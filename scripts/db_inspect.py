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
            r["gender"] or "—", r["age"] or "—",
            r["created_at"][:19] if r["created_at"] else "—",
        ))
    _hr()
    conn.close()


def cmd_records(doctor_id: str | None = None):
    conn = _connect()
    sql = """
        SELECT r.id, p.name AS patient, r.doctor_id,
               r.chief_complaint, r.diagnosis, r.created_at
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
    fmt = "{:<5} {:<10} {:<20} {:<22} {}"
    print(fmt.format("ID", "Patient", "Chief Complaint", "Diagnosis", "Created"))
    _hr()
    for r in rows:
        print(fmt.format(
            r["id"],
            (r["patient"] or "—")[:10],
            (r["chief_complaint"] or "—")[:20],
            (r["diagnosis"] or "—")[:22],
            (r["created_at"] or "—")[:19],
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
    print(f"Doctor:   {row['doctor_id']}")
    print(f"Patient:  {row['patient_name'] or '(unlinked)'} (id={row['patient_id']})")
    _hr()
    fields = [
        ("主诉",   "chief_complaint"),
        ("现病史", "history_of_present_illness"),
        ("既往史", "past_medical_history"),
        ("体格检查", "physical_examination"),
        ("辅助检查", "auxiliary_examinations"),
        ("诊断",   "diagnosis"),
        ("治疗方案", "treatment_plan"),
        ("随访计划", "follow_up_plan"),
    ]
    for label, key in fields:
        val = row[key]
        if val:
            wrapped = textwrap.fill(val, width=60, subsequent_indent="          ")
            print(f"【{label}】  {wrapped}")
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
    print(f"Gender:  {p['gender'] or '—'}    Age: {p['age'] or '—'}")
    print(f"Created: {p['created_at']}")

    rows = conn.execute(
        "SELECT id, chief_complaint, diagnosis, created_at "
        "FROM medical_records WHERE patient_id=? ORDER BY created_at DESC",
        (patient_id,),
    ).fetchall()
    print(f"\nRecords ({len(rows)}):")
    _hr()
    for r in rows:
        print(f"  #{r['id']}  [{r['created_at'][:10]}]  "
              f"{(r['chief_complaint'] or '—')[:28]}  |  {(r['diagnosis'] or '—')[:28]}")
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
