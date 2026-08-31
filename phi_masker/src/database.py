"""Database persistence layer for PHI Masker runs and detected entities.

Supports both PostgreSQL (when DATABASE_URL env var is set) and SQLite
(fallback using db_path from PipelineConfig). All public functions accept
db_path for backwards compatibility — it is ignored when DATABASE_URL is set.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL — Postgres dialect (SERIAL, %s placeholders, no AUTOINCREMENT)
# ---------------------------------------------------------------------------

_PG_DDL_RUNS = """
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

_PG_DDL_ENTITIES = """
CREATE TABLE IF NOT EXISTS masked_entities (
    id           SERIAL PRIMARY KEY,
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

_PG_DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_runs_input_file  ON runs (input_file);
CREATE INDEX IF NOT EXISTS idx_entities_run_id  ON masked_entities (run_id);
"""

# ---------------------------------------------------------------------------
# DDL — SQLite dialect (INTEGER PRIMARY KEY AUTOINCREMENT, ? placeholders)
# ---------------------------------------------------------------------------

_SQ_DDL_RUNS = """
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

_SQ_DDL_ENTITIES = """
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

_SQ_DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_runs_input_file  ON runs (input_file);
CREATE INDEX IF NOT EXISTS idx_entities_run_id  ON masked_entities (run_id);
"""


def _database_url() -> str | None:
    """Return the DATABASE_URL env var, or None if not set."""
    return os.environ.get("DATABASE_URL") or None


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

@contextmanager
def _pg_conn() -> Generator:
    """Open a psycopg2 connection from DATABASE_URL."""
    import psycopg2  # type: ignore
    conn = psycopg2.connect(_database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _sq_conn(db_path: str) -> Generator:
    """Open a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _using_postgres() -> bool:
    return _database_url() is not None


def _ph(using_pg: bool) -> str:
    """Return the correct parameter placeholder for the active DB."""
    return "%s" if using_pg else "?"


# ---------------------------------------------------------------------------
# Public API — all functions accept db_path (ignored when using Postgres)
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> None:
    """Create tables and indexes if they do not already exist."""
    if _using_postgres():
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(_PG_DDL_RUNS)
            cur.execute(_PG_DDL_ENTITIES)
            for stmt in _PG_DDL_INDEXES.strip().split("\n"):
                if stmt.strip():
                    cur.execute(stmt)
        logger.debug("PostgreSQL database initialised")
    else:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with _sq_conn(db_path) as conn:
            conn.execute(_SQ_DDL_RUNS)
            conn.execute(_SQ_DDL_ENTITIES)
            conn.executescript(_SQ_DDL_INDEXES)
        logger.debug("SQLite database initialised at '%s'", db_path)


def is_already_processed(db_path: str, input_file: str) -> bool:
    """Return True if input_file has a prior successful run in the DB."""
    pg = _using_postgres()
    ph = _ph(pg)
    sql = f"SELECT 1 FROM runs WHERE input_file = {ph} AND status = 'success' LIMIT 1"
    if pg:
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, (input_file,))
            return cur.fetchone() is not None
    else:
        with _sq_conn(db_path) as conn:
            return conn.execute(sql, (input_file,)).fetchone() is not None


def insert_run(db_path: str, run_id: str, input_file: str, started_at: str) -> None:
    """Insert a new run record with status 'running'."""
    pg = _using_postgres()
    ph = _ph(pg)
    if pg:
        sql = f"""
            INSERT INTO runs (run_id, input_file, status, started_at)
            VALUES ({ph}, {ph}, 'running', {ph})
            ON CONFLICT (run_id) DO NOTHING
        """
        with _pg_conn() as conn:
            conn.cursor().execute(sql, (run_id, input_file, started_at))
    else:
        sql = f"""
            INSERT OR IGNORE INTO runs (run_id, input_file, status, started_at)
            VALUES ({ph}, {ph}, 'running', {ph})
        """
        with _sq_conn(db_path) as conn:
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
    """Update a run record with final status and statistics."""
    pg = _using_postgres()
    ph = _ph(pg)
    sql = f"""
        UPDATE runs
        SET status = {ph},
            completed_at = {ph},
            total_rows = {ph},
            total_entities = {ph},
            quality_grade = {ph},
            processing_time_seconds = {ph}
        WHERE run_id = {ph}
    """
    params = (status, completed_at, total_rows, total_entities, quality_grade, processing_time_seconds, run_id)
    if pg:
        with _pg_conn() as conn:
            conn.cursor().execute(sql, params)
    else:
        with _sq_conn(db_path) as conn:
            conn.execute(sql, params)
    logger.debug("Run %s updated — status=%s, entities=%d", run_id, status, total_entities)


def insert_entities(
    db_path: str,
    run_id: str,
    masked_df: pd.DataFrame,
    all_entities: List[List[Dict[str, Any]]],
) -> int:
    """Bulk-insert all detected entities for a run."""
    if not any(all_entities):
        logger.debug("No entities to insert for run %s", run_id)
        return 0

    pg = _using_postgres()
    ph = _ph(pg)
    sql = f"""
        INSERT INTO masked_entities
            (run_id, audit_id, file_name, page_no,
             entity_text, entity_label, score, start_idx, end_idx)
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
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
                run_id, audit_id, file_name, page_no,
                ent.get("text", ""), ent.get("label", ""),
                ent.get("score"), ent.get("start"), ent.get("end"),
            ))

    if pg:
        with _pg_conn() as conn:
            cur = conn.cursor()
            cur.executemany(sql, rows)
    else:
        with _sq_conn(db_path) as conn:
            conn.executemany(sql, rows)

    logger.info("Inserted %d entity rows for run %s", len(rows), run_id)
    return len(rows)
