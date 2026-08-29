"""Pipeline configuration dataclass with validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional


VALID_OUTPUT_FORMATS = {"parquet", "csv", "json"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass
class PipelineConfig:
    """Configuration for the PHI masking pipeline.

    Attributes:
        input_path: Path to the input parquet file.
        output_dir: Directory where masked output files are written.
        labels_file: Path to the Markdown file containing entity labels.
        batch_size: Number of rows to process per model batch.
        min_accuracy: Minimum confidence threshold for entity detection (0.0–1.0).
        entities: Optional list of entity types to restrict detection to.
        output_format: Output file format; one of parquet, csv, json.
        log_level: Python logging level string.
    """

    input_path: str
    output_dir: str = "output"
    labels_file: str = "labels/default_labels.md"
    batch_size: int = 32
    min_accuracy: float = 0.7
    entities: Optional[List[str]] = field(default=None)
    output_format: str = "parquet"
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        """Validate all configuration fields after initialisation."""
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size}")

        if not (0.0 <= self.min_accuracy <= 1.0):
            raise ValueError(
                f"min_accuracy must be between 0.0 and 1.0, got {self.min_accuracy}"
            )

        if self.output_format not in VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"output_format must be one of {VALID_OUTPUT_FORMATS}, "
                f"got '{self.output_format}'"
            )

        if self.log_level.upper() not in VALID_LOG_LEVELS:
            raise ValueError(
                f"log_level must be one of {VALID_LOG_LEVELS}, got '{self.log_level}'"
            )
        self.log_level = self.log_level.upper()

        if self.entities is not None:
            self.entities = [e.strip().lower() for e in self.entities if e.strip()]
            if not self.entities:
                raise ValueError("entities list is empty after stripping whitespace")

    def configure_logging(self) -> None:
        """Apply the configured log level to the root logger."""
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
