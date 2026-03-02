#!/usr/bin/env python3
"""
Batch training runner: processes raw clinical cases through the agent pipeline
and verifies every case is structured and saved to the database.

Usage:
    python tools/train.py [markdown_file] [server_url]

Defaults:
    markdown_file : train/data/clinic_raw_cases_cardiology_v1.md
    server_url    : http://127.0.0.1:8000
"""

import re
import sys
import time
import os
from dataclasses import dataclass
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not found. Run: pip install httpx")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "train" / "data" / "clinic_raw_cases_cardiology_v1.md"
DB_PATH = Path(os.environ.get("PATIENTS_DB_PATH", str(ROOT / "patients.db"))).expanduser()
BASE_URL = "http://127.0.0.1:8000"
# Seconds between cases — keeps Groq free-tier TPD usage sustainable
REQUEST_DELAY = 4

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


@dataclass
class Case:
    number: str
    doctor: str
    patient: str
    text: str


def parse_cases(content: str) -> list:
    cases = []
    # Split on the horizontal rule separator
    for block in re.split(r'-{40,}', content):
        block = block.strip()
        if not block:
            continue

        num_m = re.search(r'##\s*Case\s*(\d+)', block)
        doc_m = re.search(r'\*\*医生\*\*[：:]\s*(.+)', block)
        pat_m = re.search(r'\*\*患者\*\*[：:]\s*(.+)', block)
        txt_m = re.search(r'>\s*(.+)', block, re.DOTALL)

        if not (num_m and doc_m and pat_m and txt_m):
            continue

        cases.append(Case(
            number  = num_m.group(1).strip(),
            doctor  = doc_m.group(1).strip().rstrip('\\').strip(),
            patient = pat_m.group(1).strip().rstrip('\\').strip(),
            text    = txt_m.group(1).strip(),
        ))
    return cases


def _post(base_url: str, text: str, history: list, doctor_id: str,
          _retries: int = 2) -> tuple:
    for attempt in range(_retries + 1):
        resp = httpx.post(
            f"{base_url}/api/records/chat",
            json={"text": text, "history": history, "doctor_id": doctor_id},
            timeout=60,
        )
        if resp.status_code == 429:
            wait = 30 * (attempt + 1)
            print(f"\n    {YELLOW}rate limit — waiting {wait}s…{RESET}", end=" ", flush=True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        return data["reply"], data.get("record")
    resp.raise_for_status()  # re-raise after exhausting retries


def clean_train_data() -> int:
    """Delete all patients and records written by train_* doctor IDs. Returns rows deleted."""
    import sqlite3
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM medical_records WHERE doctor_id LIKE 'train_%'")
        records_deleted = cur.rowcount
        cur.execute("DELETE FROM patients WHERE doctor_id LIKE 'train_%'")
        patients_deleted = cur.rowcount
        cur.execute("DELETE FROM doctor_contexts WHERE doctor_id LIKE 'train_%'")
        conn.commit()
        return records_deleted + patients_deleted
    finally:
        conn.close()


def verify_db(case: Case, api_record: dict) -> tuple:
    """
    Confirm the API-returned record actually landed in the database.

    Checks:
      1. A patient row exists with the correct name and doctor_id.
      2. A medical_record row is linked to that patient.
      3. chief_complaint in DB is non-empty and matches the API response.

    Returns (ok: bool, detail: str).
    """
    import sqlite3

    if not DB_PATH.exists():
        return False, "patients.db not found"

    doctor_id = f"train_{case.doctor}"
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()

        # 1. Find patient — anonymous cases matched by doctor_id only
        if case.patient != "未报姓名":
            cur.execute(
                "SELECT id, name FROM patients WHERE name = ? AND doctor_id = ? ORDER BY id DESC LIMIT 1",
                (case.patient, doctor_id),
            )
        else:
            cur.execute(
                "SELECT id, name FROM patients WHERE doctor_id = ? ORDER BY id DESC LIMIT 1",
                (doctor_id,),
            )
        row = cur.fetchone()
        if not row:
            return False, f"patient '{case.patient}' not in DB"
        patient_id, db_patient_name = row[0], row[1]

        # Verify the stored name is not garbage (e.g. question text stored as name)
        expected = "匿名患者" if case.patient == "未报姓名" else case.patient
        if db_patient_name != expected:
            return False, f"patient name mismatch: DB='{db_patient_name}' expected='{expected}'"

        # 2. Find most recent medical record for this patient
        cur.execute(
            "SELECT chief_complaint, diagnosis, treatment_plan FROM medical_records "
            "WHERE patient_id = ? ORDER BY id DESC LIMIT 1",
            (patient_id,),
        )
        rec = cur.fetchone()
        if not rec:
            return False, "medical record row missing from DB"

        db_complaint, db_diagnosis, db_treatment = rec
        if not db_complaint:
            return False, "chief_complaint is null in DB"

        # 3. Sanity-check: DB value matches what the API returned
        api_complaint = (api_record or {}).get("chief_complaint", "")
        if api_complaint and db_complaint != api_complaint:
            return False, f"DB/API mismatch: DB='{db_complaint}' API='{api_complaint}'"

        detail = db_complaint
        if db_diagnosis:
            detail += f" | dx: {db_diagnosis[:40]}"
        return True, detail
    finally:
        conn.close()


def process_case(base_url: str, case: Case) -> tuple:
    """
    Send one case through the pipeline.  Returns (ok: bool, detail: str).

    Handles three scenarios automatically:
      1. Direct add_medical_record with name in text  → done in one turn
      2. Agent asks for patient name                  → provide it, retry
      3. Agent creates patient but skips record       → resend clinical text
    """
    doctor_id = f"train_{case.doctor}"
    history: list = []

    reply, record = _post(base_url, case.text, history, doctor_id)

    # Scenario 2: agent didn't extract the name from the text
    if "叫什么名字" in reply:
        history += [
            {"role": "user",      "content": case.text},
            {"role": "assistant", "content": reply},
        ]
        # Anonymous cases: provide a placeholder so the pipeline can continue
        name_reply = case.patient if case.patient != "未报姓名" else "匿名患者"
        reply, record = _post(base_url, name_reply, history, doctor_id)

    # Scenario 3: agent filed a create_patient but produced no record
    if not record and ("建档" in reply or "✅" in reply):
        history += [
            {"role": "user",      "content": case.text},
            {"role": "assistant", "content": reply},
        ]
        reply, record = _post(base_url, case.text, history, doctor_id)

    if record and record.get("chief_complaint"):
        return True, record, record["chief_complaint"]
    return False, None, reply[:120]


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Batch training runner")
    parser.add_argument("data_path", nargs="?", default=str(DEFAULT_DATA))
    parser.add_argument("base_url",  nargs="?", default=BASE_URL)
    parser.add_argument("--cases", help="Comma-separated case numbers to run, e.g. 013,018,020")
    parser.add_argument("--clean", action="store_true", help="Delete all train_* data from DB before running")
    args = parser.parse_args()

    data_path = Path(args.data_path)
    base_url  = args.base_url.rstrip("/")
    only      = set(args.cases.split(",")) if args.cases else None

    if args.clean:
        deleted = clean_train_data()
        print(f"{YELLOW}  Cleaned {deleted} train rows from DB.{RESET}\n")

    if not data_path.exists():
        print(f"{RED}File not found: {data_path}{RESET}")
        sys.exit(1)

    cases = parse_cases(data_path.read_text(encoding="utf-8"))
    if only:
        cases = [c for c in cases if c.number in only]
    if not cases:
        print(f"{YELLOW}No cases parsed from {data_path}{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}🏥  Cardiology Training Run{RESET}")
    print(f"{GRAY}  file   : {data_path}{RESET}")
    print(f"{GRAY}  server : {base_url}{RESET}")
    print(f"{GRAY}  cases  : {len(cases)}{RESET}\n")

    results = []
    for i, case in enumerate(cases):
        if i > 0:
            time.sleep(REQUEST_DELAY)

        label = f"Case {case.number}  {case.patient}"
        print(f"  {label:<28}", end=" ", flush=True)
        try:
            api_ok, record, detail = process_case(base_url, case)
        except httpx.ConnectError:
            api_ok, record, detail = False, None, "cannot connect to server"
        except httpx.HTTPStatusError as e:
            api_ok, record, detail = False, None, f"HTTP {e.response.status_code}: {e.response.text[:80]}"
        except Exception as e:
            api_ok, record, detail = False, None, str(e)[:100]

        if api_ok:
            db_ok, db_detail = verify_db(case, record)
            if db_ok:
                tag = f"{GREEN}PASS{RESET}"
                detail = db_detail
            else:
                tag = f"{YELLOW}DB-FAIL{RESET}"
                detail = db_detail
        else:
            db_ok = False
            tag = f"{RED}FAIL{RESET}"

        ok = api_ok and db_ok
        print(f"{tag}  {GRAY}{detail}{RESET}")
        results.append((case.number, ok, detail))

    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    colour = GREEN if passed == total else (YELLOW if passed > 0 else RED)

    print(f"\n{'─'*52}")
    print(f"  {BOLD}Result: {colour}{passed}/{total} passed{RESET}")

    failed = [(n, d) for n, ok, d in results if not ok]
    if failed:
        print(f"\n  {RED}Failed:{RESET}")
        for n, d in failed:
            print(f"    Case {n}: {d}")
    else:
        print(f"  {GREEN}All cases saved successfully.{RESET}")
    print()


if __name__ == "__main__":
    main()
