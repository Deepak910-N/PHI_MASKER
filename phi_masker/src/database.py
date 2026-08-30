"""SQLite persistence layer for PHI Masker runs and detected entities."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

_DDL_RUNS = """
CREATE TABLE IF NOT EXISTS runs (
    run_id                  TEXT PRIMARY KEY,
    input_file              TEXT,
    status                  TEXT,
    started_at              TEXT,
    completed_at            TEXT,
    total_rows              INTEGER,
    total_entities          INTEGER,
    quality_grade           TEXT,
    processing_time_seconds REAL
);
"""

_DDL_ENTITIES = """
CREATE TABLE IF NOT EXISTS masked_entities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT    NOT NULL REFERENCES runs(run_id),
    audit_id     TEXT,
    file_name    TEXT,
    page_no      INTEGER,
    entity_text  TEXT,
    entity_label TEXT,
    score        REAL,
    start_idx    INTEGER,
    end_idx      INTEGER
);
"""

_DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_runs_input_file
    ON runs (input_file);
CREATE INDEX IF NOT EXISTS idx_entities_run_id
    ON masked_entities (run_id);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a new SQLite connection with WAL mode and foreign keys enabled.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open sqlite3.Connection.
    """
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    """Create the database file and tables if they do not already exist.

    Also ensures the parent directory is created. Safe to call on every
    pipeline run — uses CREATE TABLE IF NOT EXISTS.

    Args:
        db_path: Path to the SQLite database file.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.execute(_DDL_RUNS)
        conn.execute(_DDL_ENTITIES)
        conn.executescript(_DDL_INDEXES)
    logger.debug("Database initialised at '%s'", db_path)


def is_already_processed(db_path: str, input_file: str) -> bool:
    """Return True if input_file has a prior successful run in the DB.

    Args:
        db_path: Path to the SQLite database file.
        input_file: Path to the input parquet file to check.

    Returns:
        True if a run with status 'success' exists for this file.
    """
    sql = "SELECT 1 FROM runs WHERE input_file = ? AND status = 'success' LIMIT 1"
    with _connect(db_path) as conn:
        row = conn.execute(sql, (input_file,)).fetchone()
    return row is not None


def insert_run(
    db_path: str,
    run_id: str,
    input_file: str,
    started_at: str,
) -> None:
    """Insert a new run record with status 'running'.

    Args:
        db_path: Path to the SQLite database file.
        run_id: UUID string for this run.
        input_file: Path to the input parquet file.
        started_at: ISO UTC timestamp string.
    """
    sql = """
        INSERT OR IGNORE INTO runs (run_id, input_file, status, started_at)
        VALUES (?, ?, 'running', ?)
    """
    with _connect(db_path) as conn:
        conn.execute(sql, (run_id, input_file, started_at))
    logger.debug("Run %s inserted into DB", run_id)


def update_run(
    db_path: str,
    run_id: str,
    status: str,
    completed_at: str,
    total_rows: int,
    total_entities: int,
    quality_grade: str,
    processing_time_seconds: float,
) -> None:
    """Update a run record with final status and statistics.

    Args:
        db_path: Path to the SQLite database file.
        run_id: UUID string identifying the run.
        status: Final status — 'success' or 'error'.
        completed_at: ISO UTC timestamp string.
        total_rows: Number of rows processed.
        total_entities: Total entities detected.
        quality_grade: Quality grade letter (A/B/C/D).
        processing_time_seconds: Wall-clock time for the run.
    """
    sql = """
        UPDATE runs
        SET status = ?,
            completed_at = ?,
            total_rows = ?,
            total_entities = ?,
            quality_grade = ?,
            processing_time_seconds = ?
        WHERE run_id = ?
    """
    with _connect(db_path) as conn:
        conn.execute(
            sql,
            (
                status,
                completed_at,
                total_rows,
                total_entities,
                quality_grade,
                processing_time_seconds,
                run_id,
            ),
        )
    logger.debug("Run %s updated — status=%s, entities=%d", run_id, status, total_entities)


def insert_entities(
    db_path: str,
    run_id: str,
    masked_df: pd.DataFrame,
    all_entities: List[List[Dict[str, Any]]],
) -> int:
    """Bulk-insert all detected entities for a run.

    Iterates all_entities in parallel with masked_df rows (both are
    aligned by position after preprocessing resets the index).

    Args:
        db_path: Path to the SQLite database file.
        run_id: UUID string identifying the run.
        masked_df: The masked DataFrame (provides auditId, fileName, pageNo).
        all_entities: Per-row list of entity dicts from run_masking().

    Returns:
        Total number of entity rows inserted.
    """
    if not any(all_entities):
        logger.debug("No entities to insert for run %s", run_id)
        return 0

    sql = """
        INSERT INTO masked_entities
            (run_id, audit_id, file_name, page_no,
             entity_text, entity_label, score, start_idx, end_idx)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    rows = []
    for i, row_entities in enumerate(all_entities):
        if not row_entities:
            continue
        df_row = masked_df.iloc[i]
        audit_id = str(df_row.get("auditId", "") or "")
        file_name = str(df_row.get("fileName", "") or "")
        try:
            page_no = int(df_row.get("pageNo"))
        except (TypeError, ValueError):
            page_no = None

        for ent in row_entities:
            rows.append((
                run_id,
                audit_id,
                file_name,
                page_no,
                ent.get("text", ""),
                ent.get("label", ""),
                ent.get("score"),
                ent.get("start"),
                ent.get("end"),
            ))

    with _connect(db_path) as conn:
        conn.executemany(sql, rows)

    logger.info("Inserted %d entity rows for run %s", len(rows), run_id)
    return len(rows)
