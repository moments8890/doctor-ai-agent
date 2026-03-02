#!/usr/bin/env python3
"""DB seed tool — export / import patients.db to/from a portable JSON fixture.

Usage:
    python tools/seed_db.py --export                  # dump patients.db → dev/seed_data.json
    python tools/seed_db.py --import                  # load dev/seed_data.json → patients.db
    python tools/seed_db.py --reset --import          # wipe then import (clean dev reset)
    python tools/seed_db.py --reset --no-import       # wipe only
    python tools/seed_db.py --export --dry-run        # preview without writing

NOTE: dev/seed_data.json may contain real patient data.  Review before committing.
NOTE: Stop the server before importing for best results (SQLite file-level locking).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
# Ensure local package imports (e.g. `import db.models`) work regardless of cwd.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DB = Path(os.environ.get("PATIENTS_DB_PATH", str(ROOT / "patients.db"))).expanduser()
DEFAULT_FIXTURE = ROOT / "dev" / "seed_data.json"
FIXTURE_VERSION = 1

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open db_path; exit with a red error if the file does not exist."""
    if not db_path.exists():
        print(f"{RED}Error: database not found: {db_path}{RESET}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(db_path: Path) -> None:
    """Create DB tables if db_path does not yet exist (new environment).

    No-op when the DB already exists.  On failure the process exits with a
    helpful tip to run from the repo root.
    """
    if db_path.exists():
        return
    print(f"{GRAY}  DB not found — creating schema at {db_path}…{RESET}")
    try:
        from sqlalchemy import create_engine  # noqa: PLC0415
        import db.models  # noqa: F401, PLC0415
        from db.engine import Base  # noqa: PLC0415

        db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(bind=engine)
        print(f"{GREEN}  Schema created.{RESET}")
    except Exception as exc:
        print(f"{RED}  Failed to create schema: {exc}{RESET}")
        print(f"{YELLOW}  Tip: run seed_db.py from the repo root directory.{RESET}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_fixture(
    db_path: Path,
    fixture_path: Path,
    dry_run: bool = False,
) -> None:
    """Dump patients + medical_records from db_path to fixture_path as JSON."""
    conn = _connect(db_path)
    try:
        cur = conn.cursor()
        patients: List[Dict] = [
            dict(row)
            for row in cur.execute(
                "SELECT * FROM patients ORDER BY id ASC"
            ).fetchall()
        ]
        records: List[Dict] = [
            dict(row)
            for row in cur.execute(
                "SELECT * FROM medical_records ORDER BY id ASC"
            ).fetchall()
        ]
    finally:
        conn.close()

    payload: Dict = {
        "meta": {
            "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "version": FIXTURE_VERSION,
            "patients_count": len(patients),
            "records_count": len(records),
        },
        "patients": patients,
        "medical_records": records,
    }

    print(f"\n{BOLD}DB Export{RESET}")
    print(f"{GRAY}  source  : {db_path}{RESET}")
    print(f"{GRAY}  fixture : {fixture_path}{RESET}")
    print(f"  patients : {len(patients)}")
    print(f"  records  : {len(records)}")

    if dry_run:
        print(f"\n{YELLOW}  --dry-run: no file written.{RESET}")
        return

    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n{GREEN}  Written → {fixture_path}{RESET}")


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def reset_tables(db_path: Path, dry_run: bool = False) -> None:
    """DELETE all rows from patients + medical_records and reset auto-increment.

    system_prompts and doctor_contexts are intentionally left untouched.
    """
    conn = _connect(db_path)
    try:
        print(f"\n{BOLD}Reset tables{RESET}  {GRAY}({db_path}){RESET}")
        if dry_run:
            print(f"{YELLOW}  --dry-run: no changes made.{RESET}")
            return

        cur = conn.cursor()
        cur.execute("DELETE FROM medical_records")
        rec_count = cur.rowcount
        cur.execute("DELETE FROM patients")
        pat_count = cur.rowcount
        cur.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('patients', 'medical_records')"
        )
        conn.commit()
        print(f"  Deleted {pat_count} patients, {rec_count} records.")
        print(f"  Auto-increment counters reset.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_fixture(
    db_path: Path,
    fixture_path: Path,
    dry_run: bool = False,
) -> None:
    """Load fixture_path and upsert its rows into db_path.

    Patients are deduplicated on (doctor_id, name).
    Records are deduplicated on (patient_id, chief_complaint, created_at).

    The entire import is committed atomically; a crash mid-import rolls back.
    In dry-run mode no INSERT or COMMIT is issued.
    """
    if not fixture_path.exists():
        print(f"{RED}Error: fixture not found: {fixture_path}{RESET}")
        sys.exit(1)

    data: Dict = json.loads(fixture_path.read_text(encoding="utf-8"))

    # ---- Validate ----
    meta = data.get("meta", {})
    if meta.get("version") != FIXTURE_VERSION:
        print(
            f"{RED}Error: unsupported fixture version {meta.get('version')!r} "
            f"(expected {FIXTURE_VERSION}){RESET}"
        )
        sys.exit(1)

    if "patients" not in data or "medical_records" not in data:
        print(f"{RED}Error: fixture missing 'patients' or 'medical_records' keys{RESET}")
        sys.exit(1)

    fx_patients: List[Dict] = data["patients"]
    fx_records: List[Dict] = data["medical_records"]

    print(f"\n{BOLD}DB Import{RESET}")
    print(f"{GRAY}  fixture : {fixture_path}{RESET}")
    print(f"{GRAY}  dest    : {db_path}{RESET}")
    print(f"{YELLOW}  Warning : stop the server before importing for best results.{RESET}")

    if not dry_run:
        _ensure_schema(db_path)
    elif not db_path.exists():
        n_p, n_r = len(fx_patients), len(fx_records)
        print(
            f"\n{YELLOW}  (dry-run) DB does not exist — would create schema and "
            f"import {n_p} patients, {n_r} records.{RESET}"
        )
        return

    conn = _connect(db_path)
    try:
        cur = conn.cursor()

        # ---- Patient import ----
        # id_map: fixture patient id → destination DB id
        # New patients in dry_run get a negative sentinel so their records can
        # still be counted without a real DB id.
        id_map: Dict[int, int] = {}
        pat_inserted = pat_skipped = 0

        for p in fx_patients:
            fx_id: int = p["id"]
            row = cur.execute(
                "SELECT id FROM patients WHERE doctor_id IS ? AND name IS ?",
                (p.get("doctor_id"), p.get("name")),
            ).fetchone()

            if row:
                id_map[fx_id] = row[0]
                pat_skipped += 1
            else:
                year_of_birth = p.get("year_of_birth")
                age = p.get("age")
                if year_of_birth is None and age is not None:
                    try:
                        year_of_birth = datetime.now(UTC).year - int(age)
                    except (TypeError, ValueError):
                        year_of_birth = None
                if age is None and year_of_birth is not None:
                    try:
                        age = datetime.now(UTC).year - int(year_of_birth)
                    except (TypeError, ValueError):
                        age = None

                if not dry_run:
                    try:
                        cur.execute(
                            "INSERT INTO patients"
                            " (doctor_id, name, gender, year_of_birth, created_at)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (
                                p.get("doctor_id"),
                                p.get("name"),
                                p.get("gender"),
                                year_of_birth,
                                p.get("created_at"),
                            ),
                        )
                    except sqlite3.OperationalError:
                        # Backward-compatibility for older schemas that still use `age`.
                        cur.execute(
                            "INSERT INTO patients"
                            " (doctor_id, name, gender, age, created_at)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (
                                p.get("doctor_id"),
                                p.get("name"),
                                p.get("gender"),
                                age,
                                p.get("created_at"),
                            ),
                        )
                    id_map[fx_id] = cur.lastrowid
                else:
                    # Negative sentinel: unique but not a real DB id
                    id_map[fx_id] = -(pat_inserted + 1)
                pat_inserted += 1

        # ---- Record import ----
        rec_inserted = rec_skipped = 0
        null_patient_warned = False

        for r in fx_records:
            fx_patient_id: Optional[int] = r.get("patient_id")

            if fx_patient_id is None or fx_patient_id not in id_map:
                dest_patient_id: Optional[int] = None
                if fx_patient_id is not None and not null_patient_warned:
                    print(
                        f"{YELLOW}  Warning: patient_id {fx_patient_id!r} not in "
                        f"id mapping; inserting with patient_id=NULL{RESET}"
                    )
                    null_patient_warned = True
            else:
                dest_patient_id = id_map[fx_patient_id]

            # Only dedup against real (positive) DB ids.
            # Sentinel (negative) ids mean the patient is new in this run —
            # no existing records can match, so no dedup check needed.
            if dest_patient_id is None or dest_patient_id > 0:
                dup = cur.execute(
                    "SELECT id FROM medical_records"
                    " WHERE patient_id IS ? AND chief_complaint IS ? AND created_at = ?",
                    (
                        dest_patient_id,
                        r.get("chief_complaint"),
                        r.get("created_at"),
                    ),
                ).fetchone()
                if dup:
                    rec_skipped += 1
                    continue

            if not dry_run:
                # Guard: don't write sentinel ids into the DB
                db_pid: Optional[int] = (
                    dest_patient_id
                    if (dest_patient_id is None or dest_patient_id > 0)
                    else None
                )
                cur.execute(
                    "INSERT INTO medical_records"
                    " (patient_id, doctor_id, chief_complaint,"
                    "  history_of_present_illness, past_medical_history,"
                    "  physical_examination, auxiliary_examinations,"
                    "  diagnosis, treatment_plan, follow_up_plan, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        db_pid,
                        r.get("doctor_id"),
                        r.get("chief_complaint"),
                        r.get("history_of_present_illness"),
                        r.get("past_medical_history"),
                        r.get("physical_examination"),
                        r.get("auxiliary_examinations"),
                        r.get("diagnosis"),
                        r.get("treatment_plan"),
                        r.get("follow_up_plan"),
                        r.get("created_at"),
                    ),
                )
            rec_inserted += 1

        if not dry_run:
            conn.commit()

        prefix = f"{YELLOW}(dry-run) {RESET}" if dry_run else ""
        print(
            f"\n{GREEN}  {prefix}Imported: {pat_inserted} patients"
            f" ({pat_skipped} skipped),"
            f" {rec_inserted} records ({rec_skipped} skipped){RESET}"
        )

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export/import patients.db to/from a JSON seed fixture.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    action = parser.add_mutually_exclusive_group()
    action.add_argument("--export", action="store_true", help="Export DB → fixture JSON")
    action.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        help="Import fixture JSON → DB",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe patients + records before import (or alone with --no-import)",
    )
    parser.add_argument(
        "--no-import",
        dest="no_import",
        action="store_true",
        help="Skip import after reset (requires --reset)",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default=str(DEFAULT_DB),
        metavar="PATH",
        help=f"SQLite DB path (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--fixture",
        dest="fixture_path",
        default=str(DEFAULT_FIXTURE),
        metavar="PATH",
        help=f"Fixture JSON path (default: {DEFAULT_FIXTURE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only — no writes to disk or DB",
    )

    args = parser.parse_args()

    db_path = Path(args.db_path)
    fixture_path = Path(args.fixture_path)

    # Validate flag combinations
    if args.no_import and not args.reset:
        parser.error("--no-import requires --reset")

    if not args.export and not args.do_import and not args.reset:
        parser.error("Nothing to do. Use --export, --import, or --reset.")

    # Route
    if args.export:
        export_fixture(db_path, fixture_path, dry_run=args.dry_run)
        return

    if args.reset:
        reset_tables(db_path, dry_run=args.dry_run)

    if args.do_import:
        import_fixture(db_path, fixture_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
