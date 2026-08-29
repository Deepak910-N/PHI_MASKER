"""Clean and validate input data before PHI masking."""

from __future__ import annotations

import logging
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"auditId", "fileName", "pageNo", "Content"}


def validate_columns(df: pd.DataFrame) -> None:
    """Assert that the DataFrame contains all required columns.

    Args:
        df: Input DataFrame to validate.

    Raises:
        ValueError: If any required column is missing.
    """
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Input file is missing required columns: {sorted(missing)}. "
            f"Expected: {sorted(REQUIRED_COLUMNS)}"
        )


def preprocess(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, int]]:
    """Clean the input DataFrame for PHI masking.

    Steps applied in order:
        1. Validate required columns are present.
        2. Drop rows where Content is null.
        3. Drop fully-duplicate rows (all columns identical).
        4. Strip leading/trailing whitespace from Content.
        5. Drop rows where Content is empty after stripping.
        6. Reset the DataFrame index.

    Args:
        df: Raw input DataFrame loaded from the parquet file.

    Returns:
        A tuple of (cleaned DataFrame, stats dict). The stats dict contains:
            - initial_rows
            - null_content_removed
            - duplicates_removed
            - empty_content_removed
            - rows_after_preprocessing
            - total_removed
    """
    validate_columns(df)

    initial_rows = len(df)
    logger.info("Preprocessing started — initial rows: %d", initial_rows)

    # Step 1: drop null Content
    df_clean = df.dropna(subset=["Content"])
    null_removed = initial_rows - len(df_clean)
    logger.debug("Null Content rows removed: %d", null_removed)

    # Step 2: drop fully-duplicate rows
    before_dedup = len(df_clean)
    df_clean = df_clean.drop_duplicates()
    duplicates_removed = before_dedup - len(df_clean)
    logger.debug("Duplicate rows removed: %d", duplicates_removed)

    # Step 3: strip whitespace and drop empty Content
    df_clean = df_clean.copy()
    df_clean["Content"] = df_clean["Content"].astype(str).str.strip()
    before_empty = len(df_clean)
    df_clean = df_clean[df_clean["Content"] != ""]
    empty_removed = before_empty - len(df_clean)
    logger.debug("Empty Content rows removed: %d", empty_removed)

    df_clean = df_clean.reset_index(drop=True)
    rows_after = len(df_clean)
    total_removed = initial_rows - rows_after

    stats: Dict[str, int] = {
        "initial_rows": initial_rows,
        "null_content_removed": null_removed,
        "duplicates_removed": duplicates_removed,
        "empty_content_removed": empty_removed,
        "rows_after_preprocessing": rows_after,
        "total_removed": total_removed,
    }

    logger.info(
        "Preprocessing complete — rows after: %d (removed %d total)",
        rows_after,
        total_removed,
    )
    return df_clean, stats
