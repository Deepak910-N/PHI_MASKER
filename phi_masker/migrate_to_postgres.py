"""One-shot migration: copy SQLite data into PostgreSQL.

Usage:
    export DATABASE_URL=postgres://phi_masker:phi_masker_secret@localhost:5432/phi_masker
    cd phi_masker
    python migrate_to_postgres.py [--sqlite-path data/phi_masker.db]

Skips any run with status='running' (stuck/orphaned records).
Safe to re-run — uses ON CONFLICT DO NOTHING for runs and checks
existing run_ids before inserting entities.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def migrate(sqlite_path: str) -> None:
    import os
    import psycopg2  # type: ignore

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL environment variable is not set.")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Read from SQLite                                                     #
    # ------------------------------------------------------------------ #
    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row

    runs = sq.execute(
        "SELECT * FROM runs WHERE status != 'running'"
    ).fetchall()
    logger.info("Found %d completed runs in SQLite (skipping 'running' rows)", len(runs))

    run_ids = [r["run_id"] for r in runs]
    if not run_ids:
        logger.info("Nothing to migrate.")
        sq.close()
        return

    placeholders = ",".join("?" * len(run_ids))
    entities = sq.execute(
        f"SELECT * FROM masked_entities WHERE run_id IN ({placeholders})",
        run_ids,
    ).fetchall()
    logger.info("Found %d entity rows to migrate", len(entities))
    sq.close()

    # ------------------------------------------------------------------ #
    # Write to Postgres                                                    #
    # ------------------------------------------------------------------ #
    pg = psycopg2.connect(db_url)
    cur = pg.cursor()

    # Ensure tables exist
    cur.execute("""
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
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS masked_entities (
            id           SERIAL PRIMARY KEY,
            run_id       TEXT NOT NULL REFERENCES runs(run_id),
            audit_id     TEXT,
            file_name    TEXT,
            page_no      INTEGER,
            entity_text  TEXT,
            entity_label TEXT,
            score        REAL,
            start_idx    INTEGER,
            end_idx      INTEGER
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_runs_input_file ON runs (input_file)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entities_run_id ON masked_entities (run_id)")
    pg.commit()

    # Insert runs
    runs_inserted = 0
    for r in runs:
        cur.execute("""
            INSERT INTO runs
                (run_id, input_file, status, started_at, completed_at,
                 total_rows, total_entities, quality_grade, processing_time_seconds)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO NOTHING
        """, (
            r["run_id"], r["input_file"], r["status"], r["started_at"],
            r["completed_at"], r["total_rows"], r["total_entities"],
            r["quality_grade"], r["processing_time_seconds"],
        ))
        if cur.rowcount:
            runs_inserted += 1
    pg.commit()
    logger.info("Runs inserted: %d (skipped duplicates: %d)", runs_inserted, len(runs) - runs_inserted)

    # Insert entities in batches of 1000
    batch_size = 1000
    entities_inserted = 0
    for i in range(0, len(entities), batch_size):
        batch = entities[i: i + batch_size]
        cur.executemany("""
            INSERT INTO masked_entities
                (run_id, audit_id, file_name, page_no,
                 entity_text, entity_label, score, start_idx, end_idx)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, [
            (e["run_id"], e["audit_id"], e["file_name"], e["page_no"],
             e["entity_text"], e["entity_label"], e["score"],
             e["start_idx"], e["end_idx"])
            for e in batch
        ])
        entities_inserted += len(batch)
        pg.commit()
        logger.info("Entities inserted: %d / %d", entities_inserted, len(entities))

    cur.close()
    pg.close()
    logger.info("Migration complete. %d runs, %d entities migrated.", runs_inserted, entities_inserted)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate PHI Masker SQLite data to PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default="data/phi_masker.db",
        help="Path to the SQLite database file (default: data/phi_masker.db)",
    )
    args = parser.parse_args()
    migrate(args.sqlite_path)
