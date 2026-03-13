#!/usr/bin/env python3
"""
从命令行检查 patients.db 数据库内容。

Inspect patients.db from the command line.

Usage:
    python scripts/db_inspect.py patients          # list all patients
    python scripts/db_inspect.py patients doc_001  # list patients for one doctor
    python scripts/db_inspect.py records           # list recent records (all doctors)
    python scripts/db_inspect.py records doc_001   # records for one doctor
    python scripts/db_inspect.py record 42         # full detail for one record
    python scripts/db_inspect.py patient 7         # full detail for one patient + records
"""
import sqlite3
import sys
import textwrap
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("PATIENTS_DB_PATH", str(ROOT / "patients.db"))).expanduser()


def _connect():
    if not DB_PATH.exists():
        sys.exit(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _hr():
    print("─" * 72)


def _safe(row, key, default="—"):
    """Safely fetch a column value, returning default if the column doesn't exist."""
    try:
        val = row[key]
        return val if val is not None else default
    except (IndexError, KeyError):
        return default


def _age_from_yob(row):
    """Compute approximate age from year_of_birth, falling back to 'age' column for legacy DBs."""
    yob = _safe(row, "year_of_birth", None)
    if yob is not None:
        from datetime import date
        return str(date.today().year - int(yob))
    return _safe(row, "age", "—")


def cmd_patients(doctor_id: str | None = None):
    conn = _connect()
    if doctor_id:
        rows = conn.execute(
            "SELECT * FROM patients WHERE doctor_id=? ORDER BY created_at DESC",
            (doctor_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM patients ORDER BY created_at DESC"
        ).fetchall()

    title = f"Patients{' — ' + doctor_id if doctor_id else ''} ({len(rows)} rows)"
    print(f"\n{title}")
    _hr()
    fmt = "{:<5} {:<20} {:<16} {:<6} {:<5} {}"
    print(fmt.format("ID", "Name", "Doctor", "Gender", "Age", "Created"))
    _hr()
    for r in rows:
        print(fmt.format(
            r["id"], r["name"], r["doctor_id"][:16],
            _safe(r, "gender"), _age_from_yob(r),
            (r["created_at"] or "—")[:19],
        ))
    _hr()
    conn.close()


def cmd_records(doctor_id: str | None = None):
    conn = _connect()
    sql = """
        SELECT r.id, p.name AS patient, r.doctor_id,
               r.content, r.record_type, r.tags, r.created_at
        FROM medical_records r
        LEFT JOIN patients p ON r.patient_id = p.id
        {where}
        ORDER BY r.created_at DESC
        LIMIT 30
    """
    if doctor_id:
        rows = conn.execute(
            sql.format(where="WHERE r.doctor_id=?"), (doctor_id,)
        ).fetchall()
    else:
        rows = conn.execute(sql.format(where="")).fetchall()

    title = f"Records{' — ' + doctor_id if doctor_id else ''} ({len(rows)} rows, max 30)"
    print(f"\n{title}")
    _hr()
    fmt = "{:<5} {:<10} {:<8} {:<30} {}"
    print(fmt.format("ID", "Patient", "Type", "Content (preview)", "Created"))
    _hr()
    for r in rows:
        content_preview = (_safe(r, "content", "—"))[:30].replace("\n", " ")
        print(fmt.format(
            r["id"],
            (_safe(r, "patient"))[:10],
            (_safe(r, "record_type"))[:8],
            content_preview,
            (_safe(r, "created_at"))[:19],
        ))
    _hr()
    conn.close()


def cmd_record(record_id: int):
    conn = _connect()
    row = conn.execute(
        """SELECT r.*, p.name AS patient_name
           FROM medical_records r
           LEFT JOIN patients p ON r.patient_id = p.id
           WHERE r.id=?""",
        (record_id,),
    ).fetchone()
    if not row:
        sys.exit(f"Record {record_id} not found.")

    print(f"\nRecord #{row['id']}  —  {row['created_at']}")
    _hr()
    print(f"Doctor:      {row['doctor_id']}")
    print(f"Patient:     {_safe(row, 'patient_name', '(unlinked)')} (id={row['patient_id']})")
    print(f"Type:        {_safe(row, 'record_type')}")
    print(f"Tags:        {_safe(row, 'tags')}")
    _hr()
    content = _safe(row, "content", "")
    if content:
        wrapped = textwrap.fill(content, width=68, subsequent_indent="  ")
        print(f"【内容】\n  {wrapped}")
    _hr()
    conn.close()


def cmd_patient(patient_id: int):
    conn = _connect()
    p = conn.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not p:
        sys.exit(f"Patient {patient_id} not found.")

    print(f"\nPatient #{p['id']}  {p['name']}")
    _hr()
    print(f"Doctor:  {p['doctor_id']}")
    print(f"Gender:  {_safe(p, 'gender')}    Age: {_age_from_yob(p)}")
    print(f"Created: {p['created_at']}")

    rows = conn.execute(
        "SELECT id, content, record_type, created_at "
        "FROM medical_records WHERE patient_id=? ORDER BY created_at DESC",
        (patient_id,),
    ).fetchall()
    print(f"\nRecords ({len(rows)}):")
    _hr()
    for r in rows:
        content_preview = (_safe(r, "content", "—"))[:40].replace("\n", " ")
        print(f"  #{r['id']}  [{(_safe(r, 'created_at'))[:10]}]  "
              f"[{_safe(r, 'record_type')}]  {content_preview}")
    _hr()
    conn.close()


def usage():
    print(__doc__)
    sys.exit(1)


COMMANDS = {
    "patients": cmd_patients,
    "records":  cmd_records,
    "record":   cmd_record,
    "patient":  cmd_patient,
}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in COMMANDS:
        usage()

    cmd = args[0]
    rest = args[1:]

    if cmd in ("record", "patient"):
        if not rest:
            usage()
        COMMANDS[cmd](int(rest[0]))
    else:
        COMMANDS[cmd](rest[0] if rest else None)
