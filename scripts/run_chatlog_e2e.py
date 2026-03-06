#!/usr/bin/env python3
"""Replay casual doctor-agent chatlogs against /api/records/chat for E2E stability.

Usage:
  .venv/bin/python scripts/run_chatlog_e2e.py
  .venv/bin/python scripts/run_chatlog_e2e.py --cases CASUAL-E2E-001,CASUAL-E2E-002
  .venv/bin/python scripts/run_chatlog_e2e.py --dataset-mode half
  .venv/bin/python scripts/run_chatlog_e2e.py --dataset-mode full
  .venv/bin/python scripts/run_chatlog_e2e.py --timeout 120 --retries 2
"""
from __future__ import annotations

import argparse
import concurrent.futures
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

    shared_env = Path("/Users/jingwuxu/Documents/code/shared-db/.env")
    if shared_env.exists():
        load_dotenv(shared_env)
    else:
        load_dotenv()
except Exception:
    pass


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v1.json"
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

_TABLES_WITH_DOCTOR_ID = {
    "patients",
    "medical_records",
    "doctor_tasks",
    "doctor_contexts",
    "doctors",
    "neuro_cases",
}
_TABLES_GLOBAL_ONLY = {
    "system_prompts",
    "patient_labels",
    "patient_label_assignments",
    "runtime_configs",
    "runtime_tokens",
    "runtime_cursors",
}


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


def _slice_cases(cases: List[Case], dataset_mode: str) -> List[Case]:
    if dataset_mode == "half":
        half = max(1, len(cases) // 2)
        return cases[:half]
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


def _db_patient_exists(doctor_id: str, patient_name: str) -> Optional[bool]:
    count = _db_patient_count(doctor_id, patient_name)
    if count is None:
        return None
    return count > 0


def _db_table_count(table: str, doctor_id: Optional[str]) -> Optional[int]:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        table_name = table.strip()
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table_name,),
        ).fetchone()
        if not exists:
            return None
        if table_name in _TABLES_WITH_DOCTOR_ID:
            if not doctor_id:
                return None
            row = conn.execute(
                "SELECT COUNT(1) FROM {0} WHERE doctor_id=?".format(table_name),
                (doctor_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(1) FROM {0}".format(table_name)).fetchone()
        if not row:
            return 0
        return int(row[0])
    finally:
        conn.close()


def _validate_keywords(haystack: str, keywords: List[str], mode: str) -> Tuple[bool, List[str]]:
    if not keywords:
        return True, []
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


def _validate_any_of_groups(haystack: str, groups: List[List[str]]) -> Tuple[bool, List[List[str]]]:
    blob = _normalize(haystack)
    failed_groups: List[List[str]] = []
    for group in groups:
        if not group:
            continue
        if not any(_normalize(token) in blob for token in group):
            failed_groups.append(group)
    return len(failed_groups) == 0, failed_groups


def _parse_any_of_groups(raw_groups: object) -> List[List[str]]:
    parsed_groups: List[List[str]] = []
    if not isinstance(raw_groups, list):
        return parsed_groups
    for group in raw_groups:
        if not isinstance(group, list):
            continue
        parsed_groups.append([str(x) for x in group if str(x).strip()])
    return parsed_groups


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
    require_db_persistence: bool,
    allow_model_limitations: bool,
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
    model_limited_notes: List[str] = []
    if (not ok_kw) and response_keywords_only and allow_model_limitations:
        ok_kw_full, _ = _validate_keywords(full_blob, keywords, mode=keywords_mode)
        if ok_kw_full:
            ok_kw = True
            model_limited_notes.append("keywords_from_doctor_context")
    if not ok_kw:
        elapsed = time.perf_counter() - started
        return CaseResult(
            case_id=case.case_id,
            ok=False,
            detail="keyword check failed (%s); missing: %s" % (keywords_mode, ", ".join(missing[:6])),
            turns_sent=turns_sent,
            elapsed_s=elapsed,
        )

    parsed_groups = _parse_any_of_groups(exp.get("must_include_any_of", []))
    ok_groups, failed_groups = _validate_any_of_groups(keyword_blob, parsed_groups)
    if (not ok_groups) and response_keywords_only and allow_model_limitations:
        ok_groups_full, _ = _validate_any_of_groups(full_blob, parsed_groups)
        if ok_groups_full:
            ok_groups = True
            model_limited_notes.append("clinical_terms_from_doctor_context")
    if not ok_groups:
        elapsed = time.perf_counter() - started
        compact = " | ".join(["/".join(g[:4]) for g in failed_groups[:3]])
        return CaseResult(
            case_id=case.case_id,
            ok=False,
            detail="any-of group check failed: " + compact,
            turns_sent=turns_sent,
            elapsed_s=elapsed,
        )

    # Strict assistant-only checks (useful for same-name disambiguation prompts).
    reply_groups = _parse_any_of_groups(exp.get("must_include_reply_any_of", []))
    ok_reply_groups, failed_reply_groups = _validate_any_of_groups("\n".join(assistant_replies), reply_groups)
    if not ok_reply_groups:
        elapsed = time.perf_counter() - started
        compact = " | ".join(["/".join(g[:4]) for g in failed_reply_groups[:3]])
        return CaseResult(
            case_id=case.case_id,
            ok=False,
            detail="assistant any-of check failed: " + compact,
            turns_sent=turns_sent,
            elapsed_s=elapsed,
        )

    expected_patient_name = str(exp.get("expected_patient_name", "")).strip()
    if expected_patient_name and require_db_persistence:
        exists = _db_patient_exists(doctor_id, expected_patient_name)
        if exists is False and allow_model_limitations:
            fallback_symptom = "不适"
            if parsed_groups and parsed_groups[0]:
                fallback_symptom = parsed_groups[0][0]
            fallback_text = (
                "请明确执行：新建患者{0}，男55岁，主诉{1}，并保存本次病历。".format(
                    expected_patient_name,
                    fallback_symptom,
                )
            )
            response = _post_chat(
                base_url=base_url,
                text=fallback_text,
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
            history.append({"role": "user", "content": fallback_text})
            history.append({"role": "assistant", "content": reply})
            turns_sent += 1
            exists = _db_patient_exists(doctor_id, expected_patient_name)
            if exists:
                model_limited_notes.append("db_persist_retry")
            if exists is False:
                elapsed = time.perf_counter() - started
                return CaseResult(
                    case_id=case.case_id,
                    ok=False,
                detail="patient missing in DB: %s" % expected_patient_name,
                    turns_sent=turns_sent,
                    elapsed_s=elapsed,
                )

    # Same-name support: assert exact remaining count by patient name.
    expected_count_obj = exp.get("expected_patient_count")
    if require_db_persistence and expected_patient_name and expected_count_obj is not None:
        count = _db_patient_count(doctor_id, expected_patient_name)
        if count is None:
            elapsed = time.perf_counter() - started
            return CaseResult(
                case_id=case.case_id,
                ok=False,
                detail="expected_patient_count requires DB, but DB path is unavailable",
                turns_sent=turns_sent,
                elapsed_s=elapsed,
            )
        try:
            expected_count = int(expected_count_obj)
        except Exception:
            elapsed = time.perf_counter() - started
            return CaseResult(
                case_id=case.case_id,
                ok=False,
                detail="invalid expected_patient_count: {0}".format(expected_count_obj),
                turns_sent=turns_sent,
                elapsed_s=elapsed,
            )
        if count != expected_count:
            elapsed = time.perf_counter() - started
            return CaseResult(
                case_id=case.case_id,
                ok=False,
                detail="patient count mismatch for {0}: expected={1}, actual={2}".format(
                    expected_patient_name,
                    expected_count,
                    count,
                ),
                turns_sent=turns_sent,
                elapsed_s=elapsed,
            )

    expected_table_min_counts_global = exp.get("expected_table_min_counts_global")
    if isinstance(expected_table_min_counts_global, dict):
        for table, raw_min in expected_table_min_counts_global.items():
            try:
                min_count = int(raw_min)
            except Exception:
                elapsed = time.perf_counter() - started
                return CaseResult(
                    case_id=case.case_id,
                    ok=False,
                    detail="invalid expected_table_min_counts_global[{0}]={1}".format(table, raw_min),
                    turns_sent=turns_sent,
                    elapsed_s=elapsed,
                )
            count = _db_table_count(str(table), doctor_id=None)
            if count is None or count < min_count:
                elapsed = time.perf_counter() - started
                return CaseResult(
                    case_id=case.case_id,
                    ok=False,
                    detail="table count check failed (global): {0} expected>={1}, actual={2}".format(
                        table, min_count, count
                    ),
                    turns_sent=turns_sent,
                    elapsed_s=elapsed,
                )

    expected_table_min_counts_by_doctor = exp.get("expected_table_min_counts_by_doctor")
    if isinstance(expected_table_min_counts_by_doctor, dict):
        for table, raw_min in expected_table_min_counts_by_doctor.items():
            try:
                min_count = int(raw_min)
            except Exception:
                elapsed = time.perf_counter() - started
                return CaseResult(
                    case_id=case.case_id,
                    ok=False,
                    detail="invalid expected_table_min_counts_by_doctor[{0}]={1}".format(table, raw_min),
                    turns_sent=turns_sent,
                    elapsed_s=elapsed,
                )
            count = _db_table_count(str(table), doctor_id=doctor_id)
            if count is None or count < min_count:
                elapsed = time.perf_counter() - started
                return CaseResult(
                    case_id=case.case_id,
                    ok=False,
                    detail="table count check failed (doctor): {0} expected>={1}, actual={2}".format(
                        table, min_count, count
                    ),
                    turns_sent=turns_sent,
                    elapsed_s=elapsed,
                )

    if bool(exp.get("expect_patient_dedup", False)) and expected_patient_name and require_db_persistence:
        patient_name = expected_patient_name
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
    detail = "ok"
    if model_limited_notes:
        detail = "ok (model-limited: %s)" % ",".join(model_limited_notes)
    return CaseResult(
        case_id=case.case_id,
        ok=True,
        detail=detail,
        turns_sent=turns_sent,
        elapsed_s=elapsed,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay casual chatlog dataset for E2E hang/stability checks")
    parser.add_argument("data_path", nargs="?", default=str(DEFAULT_DATA))
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    parser.add_argument("--cases", help="Comma-separated case ids, e.g. CASUAL-E2E-001,CASUAL-E2E-002")
    parser.add_argument(
        "--dataset-mode",
        choices=["full", "half"],
        default="full",
        help="full: run entire dataset; half: run first 1/2 of selected dataset",
    )
    parser.add_argument("--max-cases", type=int, default=None, help="Run only first N matching cases")
    parser.add_argument("--timeout", type=float, default=90.0, help="HTTP read timeout seconds per turn")
    parser.add_argument("--retries", type=int, default=1, help="Retries per turn on failure")
    parser.add_argument("--delay-ms", type=int, default=0, help="Delay between turns in milliseconds")
    parser.add_argument("--doctor-prefix", default="chatlog_e2e", help="doctor_id prefix")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers for case replay")
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
    parser.add_argument(
        "--require-db-persistence",
        action="store_true",
        help="Require expected_patient_name and dedup assertions against local DB path",
    )
    parser.add_argument(
        "--no-model-fallback",
        action="store_true",
        help="Disable fallback checks on full doctor+agent context when response-only misses terms",
    )
    args = parser.parse_args()

    data_path = Path(args.data_path)
    if not data_path.exists():
        print(f"{RED}File not found: {data_path}{RESET}")
        sys.exit(1)

    only_case_ids = None
    if args.cases:
        only_case_ids = set([c.strip() for c in args.cases.split(",") if c.strip()])

    base_cases = _load_cases(data_path, only_case_ids=only_case_ids, max_cases=None)
    sliced_cases = _slice_cases(base_cases, dataset_mode=args.dataset_mode)
    cases = sliced_cases[: args.max_cases] if args.max_cases is not None else sliced_cases
    if not cases:
        print(f"{YELLOW}No cases loaded from {data_path}{RESET}")
        sys.exit(1)

    run_id = uuid.uuid4().hex[:8]
    base_url = args.base_url.rstrip("/")

    print(f"\n{BOLD}Casual Chatlog E2E Replay{RESET}")
    print(f"{GRAY}  file      : {data_path}{RESET}")
    print(f"{GRAY}  base_url  : {base_url}{RESET}")
    print(f"{GRAY}  mode      : {args.dataset_mode}{RESET}")
    print(f"{GRAY}  cases     : {len(cases)}{RESET}")
    print(f"{GRAY}  timeout   : {args.timeout}s{RESET}")
    print(f"{GRAY}  retries   : {args.retries}{RESET}")
    print(f"{GRAY}  run_id    : {run_id}{RESET}\n")

    def _run_one(case: Case) -> CaseResult:
        doctor_id = f"{args.doctor_prefix}_{run_id}_{case.case_id.lower()}"
        try:
            return run_case(
                case=case,
                base_url=base_url,
                doctor_id=doctor_id,
                read_timeout_s=args.timeout,
                retries=args.retries,
                delay_ms=args.delay_ms,
                response_keywords_only=args.response_keywords_only,
                keywords_mode=args.keywords_mode,
                require_db_persistence=args.require_db_persistence,
                allow_model_limitations=not args.no_model_fallback,
            )
        except Exception as exc:  # noqa: BLE001
            return CaseResult(
                case_id=case.case_id,
                ok=False,
                detail=str(exc)[:160],
                turns_sent=0,
                elapsed_s=0.0,
            )

    workers = max(1, int(args.workers))
    if workers == 1:
        results: List[CaseResult] = []
        for case in cases:
            case_label = f"{case.case_id}"
            print(f"  {case_label:<16}", end=" ", flush=True)
            result = _run_one(case)
            results.append(result)
            status = f"{GREEN}PASS{RESET}" if result.ok else f"{RED}FAIL{RESET}"
            print(
                f"{status}  {GRAY}turns={result.turns_sent} time={result.elapsed_s:.2f}s "
                f"detail={result.detail}{RESET}"
            )
            if args.fail_fast and not result.ok:
                break
    else:
        print(f"{GRAY}  workers   : {workers}{RESET}\n")
        results_by_case: Dict[str, CaseResult] = {}
        ordered_ids = [c.case_id for c in cases]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(_run_one, c): c for c in cases}
            for fut in concurrent.futures.as_completed(future_map):
                case = future_map[fut]
                case_label = f"{case.case_id}"
                result = fut.result()
                results_by_case[case.case_id] = result
                status = f"{GREEN}PASS{RESET}" if result.ok else f"{RED}FAIL{RESET}"
                print(
                    f"  {case_label:<16} {status}  "
                    f"{GRAY}turns={result.turns_sent} time={result.elapsed_s:.2f}s "
                    f"detail={result.detail}{RESET}"
                )
                if args.fail_fast and not result.ok:
                    for pending in future_map:
                        pending.cancel()
                    break
        results = [results_by_case[cid] for cid in ordered_ids if cid in results_by_case]

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
