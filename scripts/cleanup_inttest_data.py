#!/usr/bin/env python3
"""手动清理集成测试遗留的 inttest_* 数据行。

Manually purge all inttest_* rows left by integration tests.

Usage
-----
    python scripts/cleanup_inttest_data.py           # uses runtime config DB path
    python scripts/cleanup_inttest_data.py --dry-run # show counts, delete nothing
    PATIENTS_DB_PATH=/tmp/other.db python scripts/cleanup_inttest_data.py

When to use
-----------
- After cancelling a pytest run mid-way (Ctrl+C / timeout / crash)
- Before resetting a shared dev/staging database
- To verify no test debris exists

The next pytest session also sweeps automatically via the session-level
`presweep_inttest_rows` fixture in e2e/integration/conftest.py, so running
this script manually is optional — it is provided for convenience.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.runtime_config import load_runtime_json


TABLES = [
    # (table_name, column_with_doctor_id)
    ("doctor_tasks",        "doctor_id"),
    ("neuro_cases",         "doctor_id"),
    ("pending_records",     "doctor_id"),
    ("medical_records",     "doctor_id"),
    ("patients",            "doctor_id"),
    ("doctor_contexts",     "doctor_id"),
    ("doctor_session_states", "doctor_id"),
    ("conversation_turns",  "doctor_id"),
]


def _resolve_db_path() -> Path:
    env = os.environ.get("PATIENTS_DB_PATH")
    if env:
        return Path(env).expanduser()
    cfg = load_runtime_json()
    configured = cfg.get("PATIENTS_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return ROOT / "patients.db"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone())


def purge(db_path: Path, dry_run: bool = False) -> None:
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    total_deleted = 0
    try:
        for table, col in TABLES:
            if not _table_exists(conn, table):
                continue
            count_row = conn.execute(
                f"SELECT COUNT(1) FROM {table} WHERE {col} LIKE 'inttest_%'"
            ).fetchone()
            count = int(count_row[0]) if count_row else 0
            if count == 0:
                continue
            tag = "[dry-run] would delete" if dry_run else "deleted"
            print(f"  {tag} {count:>5} rows from {table}")
            if not dry_run:
                conn.execute(f"DELETE FROM {table} WHERE {col} LIKE 'inttest_%'")
            total_deleted += count

        if not dry_run:
            conn.commit()

        if total_deleted == 0:
            print("No inttest_* rows found — database is clean.")
        else:
            action = "Would remove" if dry_run else "Removed"
            print(f"\n{action} {total_deleted} rows total from {db_path}")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print counts but do not delete")
    parser.add_argument("--db", metavar="PATH", help="Override DB path")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser() if args.db else _resolve_db_path()
    print(f"Database: {db_path}")
    print(f"Mode:     {'dry-run' if args.dry_run else 'DELETE'}\n")
    purge(db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
