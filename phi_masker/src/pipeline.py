"""Orchestrates the full 6-step PHI masking pipeline."""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .config import PipelineConfig
from .database import init_db, insert_entities, insert_run, update_run
from .label_parser import parse_labels
from .masker import run_masking
from .postprocessor import (
    compute_quality_grade,
    compute_statistics,
    validate_residual_phi,
)
from .preprocessor import preprocess

logger = logging.getLogger(__name__)


class PHIMaskingPipeline:
    """End-to-end pipeline for detecting and masking PHI/PII in parquet files.

    The pipeline executes six ordered steps:
        1. Load and filter entity labels.
        2. Load and validate the input parquet file.
        3. Preprocess (deduplicate, strip, drop nulls).
        4. Detect entities and mask the Content column.
        5. Post-process: validate residual PHI, compute statistics, grade quality.
        6. Write the masked output file.

    Args:
        config: A fully-validated PipelineConfig instance.
    """

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        config.configure_logging()

    # ------------------------------------------------------------------
    # Step 1
    # ------------------------------------------------------------------
    def _load_labels(self) -> List[str]:
        """Parse and optionally filter entity labels.

        Returns:
            List of entity label strings to use for detection.

        Raises:
            ValueError: If the filtered entity list is empty.
        """
        labels = parse_labels(self.config.labels_file)
        logger.info("Loaded %d labels from '%s'", len(labels), self.config.labels_file)

        if self.config.entities:
            requested = set(self.config.entities)
            filtered = [l for l in labels if l in requested]
            if not filtered:
                raise ValueError(
                    f"None of the requested entities {sorted(requested)} "
                    f"were found in the labels file. Available: {labels}"
                )
            logger.info(
                "Filtered to %d requested entities: %s", len(filtered), filtered
            )
            return filtered

        return labels

    # ------------------------------------------------------------------
    # Step 2
    # ------------------------------------------------------------------
    def _load_input(self) -> pd.DataFrame:
        """Read and minimally validate the input parquet file.

        Returns:
            Raw DataFrame loaded from the parquet file.

        Raises:
            FileNotFoundError: If the input file does not exist.
        """
        path = Path(self.config.input_path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {self.config.input_path}")

        logger.info("Loading input file: %s", self.config.input_path)
        df = pd.read_parquet(path)
        logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))
        return df

    # ------------------------------------------------------------------
    # Step 6
    # ------------------------------------------------------------------
    def _save_output(self, df: pd.DataFrame, stem: str) -> str:
        """Write the masked DataFrame to the output directory.

        Args:
            df: Masked DataFrame to save.
            stem: Original filename stem (without extension).

        Returns:
            Absolute path to the written output file.
        """
        os.makedirs(self.config.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fmt = self.config.output_format
        filename = f"{stem}_masked_{timestamp}.{fmt}"
        output_path = os.path.join(self.config.output_dir, filename)

        if fmt == "parquet":
            df.to_parquet(output_path, index=False)
        elif fmt == "csv":
            df.to_csv(output_path, index=False)
        elif fmt == "json":
            df.to_json(output_path, orient="records", indent=2)

        logger.info("Output written to: %s", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        """Execute the full pipeline and return a results summary.

        Returns:
            A dict containing:
                run_id, status, input_file, output_file, labels_used,
                processing_time_seconds, statistics, quality_check.
        """
        start_time = time.time()
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat()
        logger.info("Pipeline started — run_id=%s, input=%s", run_id, self.config.input_path)

        # Initialise DB and insert run record (non-fatal if DB is unavailable)
        try:
            init_db(self.config.db_path)
            insert_run(self.config.db_path, run_id, self.config.input_path, started_at)
        except Exception as db_exc:
            logger.warning("DB init/insert_run failed (continuing): %s", db_exc)

        try:
            # Step 1 — Load labels
            labels = self._load_labels()

            # Step 2 — Load input
            raw_df = self._load_input()

            # Step 3 — Preprocess
            clean_df, prep_stats = preprocess(raw_df)

            # Step 4 — Detect & mask
            masked_df, all_entities = run_masking(
                clean_df,
                labels,
                batch_size=self.config.batch_size,
                min_accuracy=self.config.min_accuracy,
            )

            # Persist entities to DB (non-fatal)
            try:
                insert_entities(self.config.db_path, run_id, masked_df, all_entities)
            except Exception as db_exc:
                logger.warning("DB insert_entities failed (continuing): %s", db_exc)

            # Step 5 — Post-process
            warnings = validate_residual_phi(masked_df)
            stats = compute_statistics(masked_df, all_entities, prep_stats)
            quality = compute_quality_grade(
                avg_confidence=stats["avg_confidence"],
                validation_warnings=warnings,
                min_accuracy=self.config.min_accuracy,
            )
            stats["validation_warnings"] = warnings

            # Step 6 — Save output
            stem = Path(self.config.input_path).stem
            output_file = self._save_output(masked_df, stem)

            elapsed = round(time.time() - start_time, 2)
            logger.info("Pipeline completed in %.2fs — run_id=%s", elapsed, run_id)

            # Update run record with final stats (non-fatal)
            try:
                update_run(
                    db_path=self.config.db_path,
                    run_id=run_id,
                    status="success",
                    completed_at=datetime.utcnow().isoformat(),
                    total_rows=stats["total_rows_processed"],
                    total_entities=stats["total_entities_detected"],
                    quality_grade=quality["grade"],
                    processing_time_seconds=elapsed,
                )
            except Exception as db_exc:
                logger.warning("DB update_run failed (continuing): %s", db_exc)

            return {
                "run_id": run_id,
                "status": "success",
                "input_file": self.config.input_path,
                "output_file": output_file,
                "labels_used": labels,
                "processing_time_seconds": elapsed,
                "statistics": stats,
                "quality_check": quality,
            }

        except Exception as exc:
            elapsed = round(time.time() - start_time, 2)
            logger.error("Pipeline failed after %.2fs: %s", elapsed, exc, exc_info=True)

            try:
                update_run(
                    db_path=self.config.db_path,
                    run_id=run_id,
                    status="error",
                    completed_at=datetime.utcnow().isoformat(),
                    total_rows=0,
                    total_entities=0,
                    quality_grade="",
                    processing_time_seconds=elapsed,
                )
            except Exception as db_exc:
                logger.warning("DB update_run (error path) failed: %s", db_exc)

            return {
                "run_id": run_id,
                "status": "error",
                "input_file": self.config.input_path,
                "output_file": None,
                "labels_used": [],
                "processing_time_seconds": elapsed,
                "statistics": {},
                "quality_check": {},
                "error": str(exc),
            }
