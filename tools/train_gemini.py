#!/usr/bin/env python3
"""Batch runner for Gemini WeChat-like scenarios.

Usage:
  .venv/bin/python tools/train_gemini.py
  .venv/bin/python tools/train_gemini.py --cases GM-001,GM-003
  .venv/bin/python tools/train_gemini.py --clean --check-follow-up-tasks
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
DEFAULT_DATA = ROOT / "train" / "data" / "gemini_wechat_scenarios_v1.json"
DB_PATH = Path(os.environ.get("PATIENTS_DB_PATH", str(ROOT / "patients.db"))).expanduser()
BASE_URL = "http://127.0.0.1:8000"
REQUEST_DELAY = 2

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"


@dataclass
class Case:
    case_id: str
    title: str
    input_text: str
    expected: Dict


def _contains_all(text: Optional[str], keywords: List[str]) -> bool:
    if not keywords:
        return True
    if not text:
        return False
    return all(k in text for k in keywords)


def _contains_any(text: Optional[str], keywords: List[str]) -> bool:
    if not keywords:
        return True
    if not text:
        return False
    return any(k in text for k in keywords)


def load_cases(path: Path, only: Optional[set] = None) -> List[Case]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("JSON root must be a list")
    cases: List[Case] = []
    for item in raw:
        case = Case(
            case_id=item["case_id"],
            title=item.get("title", ""),
            input_text=item["input_text"],
            expected=item.get("expected", {}),
        )
        if only and case.case_id not in only:
            continue
        cases.append(case)
    return cases


def _post_chat(base_url: str, text: str, doctor_id: str, retries: int = 2) -> Dict:
    payload = {"text": text, "history": [], "doctor_id": doctor_id}
    last_exc: Optional[Exception] = None
    for i in range(retries + 1):
        try:
            resp = httpx.post(
                f"{base_url}/api/records/chat",
                json=payload,
                timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
            )
            if resp.status_code == 429 and i < retries:
                wait = 20 * (i + 1)
                print(f"{YELLOW}rate-limit, wait {wait}s...{RESET}")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i < retries:
                time.sleep(2)
                continue
            break
    raise RuntimeError(f"chat failed after retries: {last_exc}")


def _patient_row(doctor_id: str, patient_name: str) -> Optional[sqlite3.Row]:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT id, name, primary_risk_level
            FROM patients
            WHERE doctor_id=? AND name=?
            ORDER BY id DESC LIMIT 1
            """,
            (doctor_id, patient_name),
        ).fetchone()
    finally:
        conn.close()


def _follow_up_task(doctor_id: str, patient_id: int) -> Optional[sqlite3.Row]:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """
            SELECT id, due_at, task_type, status
            FROM doctor_tasks
            WHERE doctor_id=? AND patient_id=? AND task_type='follow_up'
            ORDER BY id DESC LIMIT 1
            """,
            (doctor_id, patient_id),
        ).fetchone()
    finally:
        conn.close()


def _due_days_ok(due_at: str, target_days: int) -> bool:
    try:
        due = datetime.fromisoformat(due_at)
    except ValueError:
        return False
    days = (due - datetime.now(timezone.utc)).days
    return abs(days - target_days) <= 2


def validate_case(case: Case, response: Dict, doctor_id: str, check_follow_up_tasks: bool) -> Tuple[bool, str]:
    expected = case.expected
    record = response.get("record")
    if not record:
        return False, "record is null"

    checks: List[Tuple[bool, str]] = [
        (_contains_all(record.get("chief_complaint"), expected.get("chief_complaint_contains", [])), "chief_complaint"),
        (_contains_any(record.get("diagnosis"), expected.get("diagnosis_contains_any", [])), "diagnosis"),
        (_contains_any(record.get("treatment_plan"), expected.get("treatment_plan_contains_any", [])), "treatment_plan"),
        (
            _contains_any(
                record.get("auxiliary_examinations"),
                expected.get("auxiliary_examinations_contains_any", []),
            ),
            "auxiliary_examinations",
        ),
        (_contains_any(record.get("follow_up_plan"), expected.get("follow_up_plan_contains_any", [])), "follow_up_plan"),
    ]
    failed = [name for ok, name in checks if not ok]
    if failed:
        return False, "field mismatch: " + ", ".join(failed)

    patient_name = expected.get("patient_name")
    patient = _patient_row(doctor_id, patient_name)
    if patient is None:
        return False, "patient not found in DB"
    if patient["primary_risk_level"] not in expected.get("risk_level_in", []):
        return False, "risk mismatch: %r" % (patient["primary_risk_level"],)

    if expected.get("expect_follow_up_task") and check_follow_up_tasks:
        task = _follow_up_task(doctor_id, int(patient["id"]))
        if task is None:
            return False, "follow_up task missing"
        if task["status"] != "pending":
            return False, "follow_up status not pending"
        target_days = int(expected.get("follow_up_task_due_days", 7))
        if not _due_days_ok(task["due_at"], target_days):
            return False, "follow_up due_at not in expected window"

    return True, (record.get("chief_complaint") or "ok")


def clean_train_rows() -> int:
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM doctor_tasks WHERE doctor_id LIKE 'train_gm_%'")
        t_deleted = cur.rowcount
        cur.execute("DELETE FROM medical_records WHERE doctor_id LIKE 'train_gm_%'")
        r_deleted = cur.rowcount
        cur.execute("DELETE FROM patients WHERE doctor_id LIKE 'train_gm_%'")
        p_deleted = cur.rowcount
        cur.execute("DELETE FROM doctor_contexts WHERE doctor_id LIKE 'train_gm_%'")
        conn.commit()
        return t_deleted + r_deleted + p_deleted
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini scenario batch runner")
    parser.add_argument("data_path", nargs="?", default=str(DEFAULT_DATA))
    parser.add_argument("base_url", nargs="?", default=BASE_URL)
    parser.add_argument("--cases", help="Comma-separated case ids, e.g. GM-001,GM-003")
    parser.add_argument("--clean", action="store_true", help="Delete train_gm_* rows before run")
    parser.add_argument("--check-follow-up-tasks", action="store_true", help="Validate follow_up tasks")
    args = parser.parse_args()

    if os.environ.get("ROUTING_LLM") != "gemini" or os.environ.get("STRUCTURING_LLM") != "gemini":
        print(f"{YELLOW}Warning: ROUTING_LLM/STRUCTURING_LLM are not both set to gemini.{RESET}")

    data_path = Path(args.data_path)
    base_url = args.base_url.rstrip("/")
    only = set([x.strip() for x in args.cases.split(",")]) if args.cases else None

    if not data_path.exists():
        print(f"{RED}File not found: {data_path}{RESET}")
        sys.exit(1)

    if args.clean:
        deleted = clean_train_rows()
        print(f"{YELLOW}Cleaned {deleted} rows{RESET}")

    cases = load_cases(data_path, only=only)
    if not cases:
        print(f"{YELLOW}No cases loaded.{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}Gemini WeChat Scenario Training Run{RESET}")
    print(f"{GRAY}  file   : {data_path}{RESET}")
    print(f"{GRAY}  server : {base_url}{RESET}")
    print(f"{GRAY}  cases  : {len(cases)}{RESET}\n")

    results: List[Tuple[str, bool, str]] = []
    for i, case in enumerate(cases):
        if i > 0:
            time.sleep(REQUEST_DELAY)
        doctor_id = "train_gm_%s_%s" % (case.case_id.lower(), uuid.uuid4().hex[:6])
        label = f"{case.case_id} {case.title}"
        print(f"  {label:<44}", end=" ", flush=True)
        try:
            response = _post_chat(base_url, case.input_text, doctor_id)
            ok, detail = validate_case(case, response, doctor_id, args.check_follow_up_tasks)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, str(exc)
        print(f"{GREEN if ok else RED}{'PASS' if ok else 'FAIL'}{RESET}  {GRAY}{detail}{RESET}")
        results.append((case.case_id, ok, detail))

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    color = GREEN if passed == total else (YELLOW if passed > 0 else RED)
    print(f"\n{'-' * 52}")
    print(f"{BOLD}Result: {color}{passed}/{total} passed{RESET}")
    if passed != total:
        print(f"\n{RED}Failed cases:{RESET}")
        for cid, ok, detail in results:
            if not ok:
                print(f"  - {cid}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    main()
