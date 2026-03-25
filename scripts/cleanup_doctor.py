#!/usr/bin/env python3
"""Delete all data for a given doctor_id (or pattern) from the local DB.

Usage:
  .venv/bin/python scripts/cleanup_doctor.py test_doctor              # dry run
  .venv/bin/python scripts/cleanup_doctor.py test_doctor --confirm    # delete
  .venv/bin/python scripts/cleanup_doctor.py --pattern "inttest_%"    # LIKE pattern
  .venv/bin/python scripts/cleanup_doctor.py --pattern "inttest_%" --confirm
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tables with doctor_id column, ordered so child rows are deleted before parents.
TABLES = [
    "medical_record_exports",
    "medical_record_versions",
    "medical_records",
    "pending_records",
    "doctor_tasks",
    "chat_archive",
    "doctor_conversation_turns",
    "doctor_contexts",
    "doctor_session_states",
    "doctor_notify_preferences",
    "doctor_knowledge_items",
    "interview_sessions",
    "patient_messages",
    "patients",
    "doctors",
]


def _find_db() -> Path:
    """Locate the SQLite DB file."""
    # Check runtime config first
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from utils.runtime_config import load_runtime_json
        cfg = load_runtime_json()
        p = cfg.get("PATIENTS_DB_PATH")
        if p:
            return Path(p).expanduser()
    except Exception:
        pass
    # Fallback
    return ROOT / "data" / "patients.db"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row and row[0])


def _has_doctor_id(conn: sqlite3.Connection, table: str) -> bool:
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        return "doctor_id" in cols
    except Exception:
        return False


def _count(conn: sqlite3.Connection, table: str, where: str, params: tuple) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0


def main():
    parser = argparse.ArgumentParser(description="Clean up doctor data from local DB")
    parser.add_argument("doctor_id", nargs="?", help="Exact doctor_id to delete")
    parser.add_argument("--pattern", help="SQL LIKE pattern (e.g. 'inttest_%%')")
    parser.add_argument("--confirm", action="store_true", help="Actually delete (default is dry run)")
    args = parser.parse_args()

    if not args.doctor_id and not args.pattern:
        parser.error("Provide a doctor_id or --pattern")

    db_path = _find_db()
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))

    # Build WHERE clause
    if args.pattern:
        where = "doctor_id LIKE ?"
        params = (args.pattern,)
        label = f"pattern '{args.pattern}'"
    else:
        where = "doctor_id = ?"
        params = (args.doctor_id,)
        label = f"doctor_id '{args.doctor_id}'"

    # Show matching doctor_ids
    try:
        rows = conn.execute(
            f"SELECT DISTINCT doctor_id FROM patients WHERE {where}", params
        ).fetchall()
        matching_ids = [r[0] for r in rows]
    except Exception:
        matching_ids = []

    if matching_ids:
        print(f"Matching doctor_ids for {label}:")
        for did in matching_ids:
            print(f"  - {did}")
    else:
        print(f"No patients found for {label}")

    # Count per table
    print()
    total = 0
    affected_tables = []
    for table in TABLES:
        if not _table_exists(conn, table) or not _has_doctor_id(conn, table):
            continue
        c = _count(conn, table, where, params)
        if c > 0:
            print(f"  {table:40s} {c:>6} rows")
            total += c
            affected_tables.append(table)

    if total == 0:
        print("Nothing to delete.")
        conn.close()
        return

    print(f"\n  {'TOTAL':40s} {total:>6} rows")

    if not args.confirm:
        print(f"\nDry run — pass --confirm to delete.")
        conn.close()
        return

    # Delete
    print(f"\nDeleting...")
    for table in affected_tables:
        c = conn.execute(f"DELETE FROM {table} WHERE {where}", params).rowcount
        print(f"  {table:40s} {c:>6} deleted")
    conn.commit()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
