#!/usr/bin/env python3
"""Replay casual doctor-agent chatlogs against /api/records/chat for E2E stability.

Usage:
  .venv/bin/python tools/run_chatlog_e2e.py
  .venv/bin/python tools/run_chatlog_e2e.py --cases CASUAL-E2E-001,CASUAL-E2E-002
  .venv/bin/python tools/run_chatlog_e2e.py --timeout 120 --retries 2
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
except Exception:
    pass


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "train" / "data" / "realworld_doctor_agent_chatlogs_e2e_v1.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DB_PATH = Path(os.environ.get("PATIENTS_DB_PATH", str(ROOT / "patients.db"))).expanduser()

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
GRAY = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

AGGRESSIVE_TREATMENT_TOKENS = [
    "急诊pci",
    "溶栓",
    "手术",
    "介入",
]


@dataclass
class Turn:
    speaker: str
    text: str


@dataclass
class Case:
    case_id: str
    title: str
    chatlog: List[Turn]
    expectations: Dict[str, object]


@dataclass
class CaseResult:
    case_id: str
    ok: bool
    detail: str
    turns_sent: int
    elapsed_s: float


def _normalize(s: str) -> str:
    return s.strip().lower()


def _join_record_text(record: Optional[Dict[str, object]]) -> str:
    if not isinstance(record, dict):
        return ""
    parts: List[str] = []
    for _, value in record.items():
        if value is None:
            continue
        parts.append(str(value))
    return "\n".join(parts)


def _load_cases(path: Path, only_case_ids: Optional[set], max_cases: Optional[int]) -> List[Case]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("JSON root must be a list")

    cases: List[Case] = []
    for item in raw:
        case_id = str(item.get("case_id", "")).strip()
        if not case_id:
            continue
        if only_case_ids and case_id not in only_case_ids:
            continue

        turns: List[Turn] = []
        for t in item.get("chatlog", []):
            speaker = str(t.get("speaker", "")).strip().lower()
            text = str(t.get("text", "")).strip()
            if not speaker or not text:
                continue
            turns.append(Turn(speaker=speaker, text=text))

        if not turns:
            continue

        cases.append(
            Case(
                case_id=case_id,
                title=str(item.get("title", "")).strip(),
                chatlog=turns,
                expectations=dict(item.get("expectations", {})),
            )
        )

        if max_cases is not None and len(cases) >= max_cases:
            break

    return cases


def _post_chat(
    base_url: str,
    text: str,
    history: List[Dict[str, str]],
    doctor_id: str,
    read_timeout_s: float,
    retries: int,
) -> Dict[str, object]:
    timeout = httpx.Timeout(connect=10.0, read=read_timeout_s, write=30.0, pool=10.0)
    payload = {"text": text, "history": history, "doctor_id": doctor_id}
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            resp = httpx.post(f"{base_url}/api/records/chat", json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(1.0)
                continue
            break

    raise RuntimeError(f"chat request failed: {last_exc}")


def _db_patient_count(doctor_id: str, patient_name: str) -> Optional[int]:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM patients WHERE doctor_id=? AND name=?",
            (doctor_id, patient_name),
        ).fetchone()
        if not row:
            return 0
        return int(row[0])
    finally:
        conn.close()


def _validate_keywords(haystack: str, keywords: List[str], mode: str) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    blob = _normalize(haystack)
    hit_count = 0
    for keyword in keywords:
        if _normalize(keyword) in blob:
            hit_count += 1
        else:
            missing.append(keyword)
    if mode == "any":
        return hit_count > 0, missing
    return len(missing) == 0, missing


def _validate_non_aggressive(treatment_text: str) -> Tuple[bool, List[str]]:
    blob = _normalize(treatment_text)
    hit: List[str] = []
    for token in AGGRESSIVE_TREATMENT_TOKENS:
        if token in blob:
            hit.append(token)
    return len(hit) == 0, hit


def run_case(
    case: Case,
    base_url: str,
    doctor_id: str,
    read_timeout_s: float,
    retries: int,
    delay_ms: int,
    response_keywords_only: bool,
    keywords_mode: str,
) -> CaseResult:
    started = time.perf_counter()
    history: List[Dict[str, str]] = []
    assistant_replies: List[str] = []
    record_texts: List[str] = []
    doctor_texts: List[str] = []
    last_record: Optional[Dict[str, object]] = None
    turns_sent = 0

    for turn in case.chatlog:
        if turn.speaker != "doctor":
            continue

        turns_sent += 1
        doctor_texts.append(turn.text)
        response = _post_chat(
            base_url=base_url,
            text=turn.text,
            history=history,
            doctor_id=doctor_id,
            read_timeout_s=read_timeout_s,
            retries=retries,
        )
        reply = str(response.get("reply", "")).strip()
        record = response.get("record")
        if isinstance(record, dict):
            last_record = record
            record_texts.append(_join_record_text(record))

        assistant_replies.append(reply)
        history.append({"role": "user", "content": turn.text})
        history.append({"role": "assistant", "content": reply})

        if delay_ms > 0:
            time.sleep(float(delay_ms) / 1000.0)

    exp = case.expectations
    assistant_blob = "\n".join(assistant_replies + record_texts)
    full_blob = "\n".join(doctor_texts + assistant_replies + record_texts)
    keyword_blob = assistant_blob if response_keywords_only else full_blob

    keywords = [str(x) for x in exp.get("must_include_keywords", [])]
    ok_kw, missing = _validate_keywords(keyword_blob, keywords, mode=keywords_mode)
    if not ok_kw:
        elapsed = time.perf_counter() - started
        return CaseResult(
            case_id=case.case_id,
            ok=False,
            detail="keyword check failed (%s); missing: %s" % (keywords_mode, ", ".join(missing[:6])),
            turns_sent=turns_sent,
            elapsed_s=elapsed,
        )

    if bool(exp.get("expect_patient_dedup", False)) and keywords:
        patient_name = keywords[0]
        count = _db_patient_count(doctor_id, patient_name)
        if count is not None and count > 1:
            elapsed = time.perf_counter() - started
            return CaseResult(
                case_id=case.case_id,
                ok=False,
                detail="dedup check failed: patient rows=%s (%s)" % (count, patient_name),
                turns_sent=turns_sent,
                elapsed_s=elapsed,
            )

    if bool(exp.get("expect_no_aggressive_treatment", False)):
        treatment_text = ""
        if isinstance(last_record, dict):
            treatment_text = str(last_record.get("treatment_plan", "") or "")
        no_aggressive, hits = _validate_non_aggressive(treatment_text)
        if not no_aggressive:
            elapsed = time.perf_counter() - started
            return CaseResult(
                case_id=case.case_id,
                ok=False,
                detail="aggressive treatment detected: " + ", ".join(hits),
                turns_sent=turns_sent,
                elapsed_s=elapsed,
            )

    elapsed = time.perf_counter() - started
    return CaseResult(
        case_id=case.case_id,
        ok=True,
        detail="ok",
        turns_sent=turns_sent,
        elapsed_s=elapsed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay casual chatlog dataset for E2E hang/stability checks")
    parser.add_argument("data_path", nargs="?", default=str(DEFAULT_DATA))
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--cases", help="Comma-separated case ids, e.g. CASUAL-E2E-001,CASUAL-E2E-002")
    parser.add_argument("--max-cases", type=int, default=None, help="Run only first N matching cases")
    parser.add_argument("--timeout", type=float, default=90.0, help="HTTP read timeout seconds per turn")
    parser.add_argument("--retries", type=int, default=1, help="Retries per turn on failure")
    parser.add_argument("--delay-ms", type=int, default=0, help="Delay between turns in milliseconds")
    parser.add_argument("--doctor-prefix", default="chatlog_e2e", help="doctor_id prefix")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after first failing case")
    parser.add_argument(
        "--response-keywords-only",
        action="store_true",
        help="Validate must_include_keywords only in agent replies + structured record",
    )
    parser.add_argument(
        "--keywords-mode",
        choices=["any", "all"],
        default="any",
        help="Keyword validation mode for must_include_keywords (default: any)",
    )
    args = parser.parse_args()

    data_path = Path(args.data_path)
    if not data_path.exists():
        print(f"{RED}File not found: {data_path}{RESET}")
        sys.exit(1)

    only_case_ids = None
    if args.cases:
        only_case_ids = set([c.strip() for c in args.cases.split(",") if c.strip()])

    cases = _load_cases(data_path, only_case_ids=only_case_ids, max_cases=args.max_cases)
    if not cases:
        print(f"{YELLOW}No cases loaded from {data_path}{RESET}")
        sys.exit(1)

    run_id = uuid.uuid4().hex[:8]
    base_url = args.base_url.rstrip("/")

    print(f"\n{BOLD}Casual Chatlog E2E Replay{RESET}")
    print(f"{GRAY}  file      : {data_path}{RESET}")
    print(f"{GRAY}  base_url  : {base_url}{RESET}")
    print(f"{GRAY}  cases     : {len(cases)}{RESET}")
    print(f"{GRAY}  timeout   : {args.timeout}s{RESET}")
    print(f"{GRAY}  retries   : {args.retries}{RESET}")
    print(f"{GRAY}  run_id    : {run_id}{RESET}\n")

    results: List[CaseResult] = []
    for case in cases:
        doctor_id = f"{args.doctor_prefix}_{run_id}_{case.case_id.lower()}"
        case_label = f"{case.case_id}"
        print(f"  {case_label:<16}", end=" ", flush=True)

        try:
            result = run_case(
                case=case,
                base_url=base_url,
                doctor_id=doctor_id,
                read_timeout_s=args.timeout,
                retries=args.retries,
                delay_ms=args.delay_ms,
                response_keywords_only=args.response_keywords_only,
                keywords_mode=args.keywords_mode,
            )
        except Exception as exc:  # noqa: BLE001
            result = CaseResult(
                case_id=case.case_id,
                ok=False,
                detail=str(exc)[:160],
                turns_sent=0,
                elapsed_s=0.0,
            )

        results.append(result)
        status = f"{GREEN}PASS{RESET}" if result.ok else f"{RED}FAIL{RESET}"
        print(
            f"{status}  {GRAY}turns={result.turns_sent} time={result.elapsed_s:.2f}s "
            f"detail={result.detail}{RESET}"
        )

        if args.fail_fast and not result.ok:
            break

    total = len(results)
    passed = len([r for r in results if r.ok])
    failed = total - passed
    total_time = sum(r.elapsed_s for r in results)
    color = GREEN if failed == 0 else (YELLOW if passed > 0 else RED)

    print(f"\n{'-' * 60}")
    print(
        f"{BOLD}Summary:{RESET} {color}{passed}/{total} passed{RESET}  "
        f"{GRAY}(failed={failed}, total_time={total_time:.2f}s){RESET}"
    )

    if failed:
        print(f"\n{RED}Failures:{RESET}")
        for r in results:
            if r.ok:
                continue
            print(f"  - {r.case_id}: {r.detail}")
        sys.exit(1)


if __name__ == "__main__":
    main()
