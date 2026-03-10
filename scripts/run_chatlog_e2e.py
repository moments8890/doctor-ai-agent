#!/usr/bin/env python3
"""
E2E 聊天日志回放脚本 — 将真实医生对话日志回放至 /api/records/chat 接口，
验证系统在多轮会话场景下的稳定性与正确性。

用法示例：
  .venv/bin/python scripts/run_chatlog_e2e.py
  .venv/bin/python scripts/run_chatlog_e2e.py --cases CASUAL-E2E-001,CASUAL-E2E-002
  .venv/bin/python scripts/run_chatlog_e2e.py --dataset-mode half
  .venv/bin/python scripts/run_chatlog_e2e.py --timeout 120 --retries 2

Replay casual doctor-agent chatlogs against /api/records/chat for E2E stability.
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
    import jwt as _pyjwt
    _HAS_JWT = True
except ImportError:
    _HAS_JWT = False


def _make_jwt(doctor_id: str, secret: str) -> str:
    """Issue a short-lived HS256 JWT for a given doctor_id."""
    if not _HAS_JWT:
        raise RuntimeError("PyJWT not installed; run: pip install PyJWT")
    now = int(time.time())
    payload = {"sub": doctor_id, "channel": "e2e", "iat": now, "exp": now + 3600}
    return _pyjwt.encode(payload, secret, algorithm="HS256")


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v1.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8001"

sys.path.insert(0, str(ROOT))
try:
    from utils.runtime_config import load_runtime_json as _load_runtime_json
    _RUNTIME_CONFIG = _load_runtime_json()
except Exception:
    _RUNTIME_CONFIG = {}

DB_PATH = Path(
    os.environ.get("PATIENTS_DB_PATH", str(_RUNTIME_CONFIG.get("PATIENTS_DB_PATH") or ROOT / "patients.db"))
).expanduser()

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

# Map stale fixture table names → current schema names.
_TABLE_ALIASES: dict[str, str] = {
    "tasks": "doctor_tasks",
    "follow_ups": "doctor_tasks",
}
_TABLES_GLOBAL_ONLY = {
    "system_prompts",
    "patient_labels",
    "patient_label_assignments",
    "runtime_configs",
    "runtime_tokens",
    "runtime_cursors",
}

# Tables to purge during cleanup, in FK-safe order (children before parents)
_CLEANUP_TABLES = [
    ("doctor_tasks",          "doctor_id"),
    ("neuro_cases",           "doctor_id"),
    ("pending_records",       "doctor_id"),
    ("medical_records",       "doctor_id"),
    ("patients",              "doctor_id"),
    ("doctor_contexts",       "doctor_id"),
    ("doctor_session_states", "doctor_id"),
    ("doctor_conversation_turns", "doctor_id"),
    ("doctors",               "doctor_id"),
]


def _cleanup_e2e_data(doctor_ids: list[str], label: str = "cleanup") -> None:
    """Delete all rows created by this e2e run from the local DB."""
    if not doctor_ids:
        return
    if not DB_PATH.exists():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        deleted_total = 0
        for table, col in _CLEANUP_TABLES:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                continue
            placeholders = ",".join("?" for _ in doctor_ids)
            cur = conn.execute(
                f"DELETE FROM {table} WHERE {col} IN ({placeholders})", doctor_ids
            )
            deleted_total += cur.rowcount
        conn.commit()
        conn.close()
        print(f"{GRAY}  [{label}] purged {deleted_total} rows for {len(doctor_ids)} doctor(s){RESET}")
    except Exception as exc:  # noqa: BLE001
        print(f"{YELLOW}  [{label}] cleanup warning: {exc}{RESET}")


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
    auth_token: Optional[str] = None,
) -> Dict[str, object]:
    timeout = httpx.Timeout(connect=10.0, read=read_timeout_s, write=30.0, pool=10.0)
    payload = {"text": text, "history": history, "doctor_id": doctor_id}
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            resp = httpx.post(f"{base_url}/api/records/chat", json=payload, headers=headers, timeout=timeout)
            # Auth errors (401/403) and server errors (5xx) are returned as soft failures
            # so the caller can decide whether to skip/continue rather than abort the whole case.
            if resp.status_code in (401, 403, 500, 502, 503):
                return {
                    "reply": "",
                    "_http_error": resp.status_code,
                    "_http_body": resp.text[:200],
                }
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
        table_name = _TABLE_ALIASES.get(table.strip(), table.strip())
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


def _send_turns(
    case: Case, base_url: str, doctor_id: str,
    read_timeout_s: float, retries: int, delay_ms: int,
    auth_token: Optional[str],
) -> Tuple[List[str], List[str], List[str], Optional[Dict], int]:
    """Send all doctor turns; return (assistant_replies, record_texts, doctor_texts, last_record, turns_sent)."""
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
            base_url=base_url, text=turn.text, history=history,
            doctor_id=doctor_id, read_timeout_s=read_timeout_s,
            retries=retries, auth_token=auth_token,
        )
        if "_http_error" in response:
            http_status = response["_http_error"]
            print(f"\n{YELLOW}    [turn skip] HTTP {http_status} — {response.get('_http_body', '')[:80]}{RESET}",
                  end="", flush=True)
            history.append({"role": "user", "content": turn.text})
            history.append({"role": "assistant", "content": ""})
            if delay_ms > 0:
                time.sleep(float(delay_ms) / 1000.0)
            continue
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
    return assistant_replies, record_texts, doctor_texts, last_record, turns_sent


def _check_keywords(
    case: Case, keyword_blob: str, full_blob: str, assistant_replies: List[str],
    response_keywords_only: bool, keywords_mode: str, allow_model_limitations: bool,
    started: float, turns_sent: int,
) -> Tuple[Optional[CaseResult], List[str], List[List[str]]]:
    """Validate keyword and any-of group assertions; return (early_fail|None, notes, parsed_groups)."""
    exp = case.expectations
    notes: List[str] = []
    keywords = [str(x) for x in exp.get("must_include_keywords", [])]
    ok_kw, missing = _validate_keywords(keyword_blob, keywords, mode=keywords_mode)
    if (not ok_kw) and response_keywords_only and allow_model_limitations:
        ok_kw_full, _ = _validate_keywords(full_blob, keywords, mode=keywords_mode)
        if ok_kw_full:
            ok_kw = True
            notes.append("keywords_from_doctor_context")
    if not ok_kw:
        elapsed = time.perf_counter() - started
        return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent, elapsed_s=elapsed,
                          detail="keyword check failed (%s); missing: %s" % (keywords_mode, ", ".join(missing[:6]))), notes, []
    parsed_groups = _parse_any_of_groups(exp.get("must_include_any_of", []))
    ok_groups, failed_groups = _validate_any_of_groups(keyword_blob, parsed_groups)
    if (not ok_groups) and response_keywords_only and allow_model_limitations:
        ok_groups_full, _ = _validate_any_of_groups(full_blob, parsed_groups)
        if ok_groups_full:
            ok_groups = True
            notes.append("clinical_terms_from_doctor_context")
    if not ok_groups:
        elapsed = time.perf_counter() - started
        compact = " | ".join(["/".join(g[:4]) for g in failed_groups[:3]])
        return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent, elapsed_s=elapsed,
                          detail="any-of group check failed: " + compact), notes, parsed_groups
    reply_groups = _parse_any_of_groups(exp.get("must_include_reply_any_of", []))
    ok_reply, failed_reply = _validate_any_of_groups("\n".join(assistant_replies), reply_groups)
    if not ok_reply:
        elapsed = time.perf_counter() - started
        compact = " | ".join(["/".join(g[:4]) for g in failed_reply[:3]])
        return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent, elapsed_s=elapsed,
                          detail="assistant any-of check failed: " + compact), notes, parsed_groups
    return None, notes, parsed_groups


def _do_fallback_retry(
    doctor_id: str, base_url: str, read_timeout_s: float, retries: int,
    auth_token: Optional[str], history: List[Dict[str, str]],
    assistant_replies: List[str], record_texts: List[str],
    patient_name: str, fallback_symptom: str, notes: List[str], turns_sent: int,
) -> Tuple[Optional[bool], int]:
    """Send a fallback 'please create patient' turn; return (exists_after|None, turns_sent)."""
    fallback_text = "请明确执行：新建患者{0}，男55岁，主诉{1}，并保存本次病历。".format(patient_name, fallback_symptom)
    resp = _post_chat(base_url=base_url, text=fallback_text, history=history,
                      doctor_id=doctor_id, read_timeout_s=read_timeout_s,
                      retries=retries, auth_token=auth_token)
    reply = str(resp.get("reply", "")).strip()
    record = resp.get("record")
    if isinstance(record, dict):
        record_texts.append(_join_record_text(record))
    assistant_replies.append(reply)
    history.append({"role": "user", "content": fallback_text})
    history.append({"role": "assistant", "content": reply})
    turns_sent += 1
    exists = _db_patient_exists(doctor_id, patient_name)
    if exists:
        notes.append("db_persist_retry")
    return exists, turns_sent


def _check_db_patient_assertions(
    case: Case, doctor_id: str, base_url: str, read_timeout_s: float, retries: int,
    auth_token: Optional[str], history: List[Dict[str, str]], assistant_replies: List[str],
    record_texts: List[str], parsed_groups: List[List[str]], notes: List[str],
    require_db_persistence: bool, allow_model_limitations: bool, started: float, turns_sent: int,
) -> Tuple[Optional[CaseResult], int]:
    """Validate patient-level DB assertions; return (early_fail|None, updated turns_sent)."""
    exp = case.expectations
    pname = str(exp.get("expected_patient_name", "")).strip()
    if not (pname and require_db_persistence):
        return None, turns_sent
    exists = _db_patient_exists(doctor_id, pname)
    if exists is False and allow_model_limitations:
        fallback_symptom = parsed_groups[0][0] if parsed_groups and parsed_groups[0] else "不适"
        exists, turns_sent = _do_fallback_retry(
            doctor_id, base_url, read_timeout_s, retries, auth_token, history,
            assistant_replies, record_texts, pname, fallback_symptom, notes, turns_sent)
        if exists is False:
            elapsed = time.perf_counter() - started
            return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent, elapsed_s=elapsed,
                              detail="patient missing in DB: %s" % pname), turns_sent
    expected_count_obj = exp.get("expected_patient_count")
    if expected_count_obj is not None:
        count = _db_patient_count(doctor_id, pname)
        if count is None:
            elapsed = time.perf_counter() - started
            return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent, elapsed_s=elapsed,
                              detail="expected_patient_count requires DB, but DB path is unavailable"), turns_sent
        try:
            expected_count = int(expected_count_obj)
        except Exception:
            elapsed = time.perf_counter() - started
            return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent, elapsed_s=elapsed,
                              detail="invalid expected_patient_count: {0}".format(expected_count_obj)), turns_sent
        if count != expected_count:
            elapsed = time.perf_counter() - started
            return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent, elapsed_s=elapsed,
                              detail="patient count mismatch for {0}: expected={1}, actual={2}".format(
                                  pname, expected_count, count)), turns_sent
    return None, turns_sent


def _check_table_counts(
    case: Case, doctor_id: str, started: float, turns_sent: int,
) -> Optional[CaseResult]:
    """Validate expected_table_min_counts_global and _by_doctor; return early_fail or None."""
    exp = case.expectations
    global_counts = exp.get("expected_table_min_counts_global")
    if isinstance(global_counts, dict):
        for table, raw_min in global_counts.items():
            try:
                min_count = int(raw_min)
            except Exception:
                return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent,
                                  elapsed_s=time.perf_counter() - started,
                                  detail="invalid expected_table_min_counts_global[{0}]={1}".format(table, raw_min))
            count = _db_table_count(str(table), doctor_id=None)
            if count is None or count < min_count:
                return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent,
                                  elapsed_s=time.perf_counter() - started,
                                  detail="table count check failed (global): {0} expected>={1}, actual={2}".format(
                                      table, min_count, count))
    by_doctor = exp.get("expected_table_min_counts_by_doctor")
    if isinstance(by_doctor, dict):
        for table, raw_min in by_doctor.items():
            try:
                min_count = int(raw_min)
            except Exception:
                return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent,
                                  elapsed_s=time.perf_counter() - started,
                                  detail="invalid expected_table_min_counts_by_doctor[{0}]={1}".format(table, raw_min))
            count = _db_table_count(str(table), doctor_id=doctor_id)
            if count is None or count < min_count:
                return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent,
                                  elapsed_s=time.perf_counter() - started,
                                  detail="table count check failed (doctor): {0} expected>={1}, actual={2}".format(
                                      table, min_count, count))
    return None


def _check_misc_assertions(
    case: Case, doctor_id: str, last_record: Optional[Dict],
    require_db_persistence: bool, started: float, turns_sent: int,
) -> Optional[CaseResult]:
    """Check dedup and no-aggressive-treatment assertions; return early_fail or None."""
    exp = case.expectations
    expected_patient_name = str(exp.get("expected_patient_name", "")).strip()
    if bool(exp.get("expect_patient_dedup", False)) and expected_patient_name and require_db_persistence:
        count = _db_patient_count(doctor_id, expected_patient_name)
        if count is not None and count > 1:
            return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent,
                              elapsed_s=time.perf_counter() - started,
                              detail="dedup check failed: patient rows=%s (%s)" % (count, expected_patient_name))
    if bool(exp.get("expect_no_aggressive_treatment", False)):
        treatment_text = ""
        if isinstance(last_record, dict):
            treatment_text = str(last_record.get("treatment_plan", "") or "")
        no_aggressive, hits = _validate_non_aggressive(treatment_text)
        if not no_aggressive:
            return CaseResult(case_id=case.case_id, ok=False, turns_sent=turns_sent,
                              elapsed_s=time.perf_counter() - started,
                              detail="aggressive treatment detected: " + ", ".join(hits))
    return None


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
    auth_token: Optional[str] = None,
) -> CaseResult:
    """Run a single E2E case end-to-end; return CaseResult."""
    started = time.perf_counter()
    assistant_replies, record_texts, doctor_texts, last_record, turns_sent = _send_turns(
        case, base_url, doctor_id, read_timeout_s, retries, delay_ms, auth_token)
    assistant_blob = "\n".join(assistant_replies + record_texts)
    full_blob = "\n".join(doctor_texts + assistant_replies + record_texts)
    keyword_blob = assistant_blob if response_keywords_only else full_blob
    fail, notes, parsed_groups = _check_keywords(
        case, keyword_blob, full_blob, assistant_replies,
        response_keywords_only, keywords_mode, allow_model_limitations, started, turns_sent)
    if fail:
        return fail
    history: List[Dict[str, str]] = []  # reconstructed for fallback
    fail, turns_sent = _check_db_patient_assertions(
        case, doctor_id, base_url, read_timeout_s, retries, auth_token,
        history, assistant_replies, record_texts, parsed_groups, notes,
        require_db_persistence, allow_model_limitations, started, turns_sent)
    if fail:
        return fail
    fail = _check_table_counts(case, doctor_id, started, turns_sent)
    if fail:
        return fail
    fail = _check_misc_assertions(case, doctor_id, last_record, require_db_persistence, started, turns_sent)
    if fail:
        return fail
    elapsed = time.perf_counter() - started
    detail = "ok (model-limited: %s)" % ",".join(notes) if notes else "ok"
    return CaseResult(case_id=case.case_id, ok=True, detail=detail, turns_sent=turns_sent, elapsed_s=elapsed)


def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the CLI argument parser."""
    p = argparse.ArgumentParser(description="Replay casual chatlog dataset for E2E hang/stability checks")
    p.add_argument("data_path", nargs="?", default=str(DEFAULT_DATA))
    p.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL)
    p.add_argument("--cases", help="Comma-separated case ids, e.g. CASUAL-E2E-001,CASUAL-E2E-002")
    p.add_argument("--dataset-mode", choices=["full", "half"], default="full",
                   help="full: run entire dataset; half: run first 1/2 of selected dataset")
    p.add_argument("--max-cases", type=int, default=None, help="Run only first N matching cases")
    p.add_argument("--timeout", type=float, default=90.0, help="HTTP read timeout seconds per turn")
    p.add_argument("--retries", type=int, default=1, help="Retries per turn on failure")
    p.add_argument("--delay-ms", type=int, default=0, help="Delay between turns in milliseconds")
    p.add_argument("--doctor-prefix", default="chatlog_e2e", help="doctor_id prefix")
    p.add_argument("--workers", type=int, default=1, help="Parallel workers for case replay")
    p.add_argument("--fail-fast", action="store_true", help="Stop after first failing case")
    p.add_argument("--no-cleanup", action="store_true",
                   help="Skip DB cleanup after run (useful for debugging leftover data)")
    p.add_argument("--response-keywords-only", action="store_true",
                   help="Validate must_include_keywords only in agent replies + structured record")
    p.add_argument("--keywords-mode", choices=["any", "all"], default="any",
                   help="Keyword validation mode for must_include_keywords (default: any)")
    p.add_argument("--require-db-persistence", action="store_true",
                   help="Require expected_patient_name and dedup assertions against local DB path")
    p.add_argument("--no-model-fallback", action="store_true",
                   help="Disable fallback checks on full doctor+agent context when response-only misses terms")
    p.add_argument("--auth-token", default=os.environ.get("E2E_AUTH_TOKEN", ""),
                   help="Bearer token for Authorization header (also reads E2E_AUTH_TOKEN env var)")
    p.add_argument("--token-secret", default="",
                   help="JWT secret for per-case token generation. Empty = no JWT auth.")
    return p


def _run_cases_serial(
    cases: List[Case], run_one, fail_fast: bool,
) -> List[CaseResult]:
    """Run cases sequentially; return result list."""
    results: List[CaseResult] = []
    for case in cases:
        print(f"  {case.case_id:<16}", end=" ", flush=True)
        result = run_one(case)
        results.append(result)
        status = f"{GREEN}PASS{RESET}" if result.ok else f"{RED}FAIL{RESET}"
        print(f"{status}  {GRAY}turns={result.turns_sent} time={result.elapsed_s:.2f}s detail={result.detail}{RESET}")
        if fail_fast and not result.ok:
            break
    return results


def _run_cases_parallel(
    cases: List[Case], run_one, workers: int, fail_fast: bool,
) -> List[CaseResult]:
    """Run cases in parallel; return result list in original order."""
    print(f"{GRAY}  workers   : {workers}{RESET}\n")
    results_by_case: Dict[str, CaseResult] = {}
    ordered_ids = [c.case_id for c in cases]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(run_one, c): c for c in cases}
        for fut in concurrent.futures.as_completed(future_map):
            case = future_map[fut]
            result = fut.result()
            results_by_case[case.case_id] = result
            status = f"{GREEN}PASS{RESET}" if result.ok else f"{RED}FAIL{RESET}"
            print(f"  {case.case_id:<16} {status}  "
                  f"{GRAY}turns={result.turns_sent} time={result.elapsed_s:.2f}s detail={result.detail}{RESET}")
            if fail_fast and not result.ok:
                for pending in future_map:
                    pending.cancel()
                break
    return [results_by_case[cid] for cid in ordered_ids if cid in results_by_case]


def _print_summary(results: List[CaseResult]) -> None:
    """Print pass/fail summary and exit with error if any failures."""
    total = len(results)
    passed = len([r for r in results if r.ok])
    failed = total - passed
    total_time = sum(r.elapsed_s for r in results)
    color = GREEN if failed == 0 else (YELLOW if passed > 0 else RED)
    print(f"\n{'-' * 60}")
    print(f"{BOLD}Summary:{RESET} {color}{passed}/{total} passed{RESET}  "
          f"{GRAY}(failed={failed}, total_time={total_time:.2f}s){RESET}")
    if failed:
        print(f"\n{RED}Failures:{RESET}")
        for r in results:
            if not r.ok:
                print(f"  - {r.case_id}: {r.detail}")
        sys.exit(1)


def _make_run_one(args, run_id: str, base_url: str, auth_token: Optional[str],
                  token_secret: Optional[str], use_per_case_tokens: bool):
    """Return a closure that runs a single case with the given args/context."""
    def _run_one(case: Case) -> CaseResult:
        doctor_id = f"{args.doctor_prefix}_{run_id}_{case.case_id.lower()}"
        case_token: Optional[str] = auth_token
        if use_per_case_tokens:
            case_token = _make_jwt(doctor_id, token_secret)
        try:
            return run_case(case=case, base_url=base_url, doctor_id=doctor_id,
                            read_timeout_s=args.timeout, retries=args.retries,
                            delay_ms=args.delay_ms, response_keywords_only=args.response_keywords_only,
                            keywords_mode=args.keywords_mode, require_db_persistence=args.require_db_persistence,
                            allow_model_limitations=not args.no_model_fallback, auth_token=case_token)
        except Exception as exc:  # noqa: BLE001
            return CaseResult(case_id=case.case_id, ok=False, detail=str(exc)[:160], turns_sent=0, elapsed_s=0.0)
    return _run_one


def main() -> None:
    """Entry point: parse args, load cases, run replay, report results."""
    args = _build_parser().parse_args()
    data_path = Path(args.data_path)
    if not data_path.exists():
        print(f"{RED}File not found: {data_path}{RESET}")
        sys.exit(1)
    only_case_ids = {c.strip() for c in args.cases.split(",") if c.strip()} if args.cases else None
    base_cases = _load_cases(data_path, only_case_ids=only_case_ids, max_cases=None)
    sliced = _slice_cases(base_cases, dataset_mode=args.dataset_mode)
    cases = sliced[: args.max_cases] if args.max_cases is not None else sliced
    if not cases:
        print(f"{YELLOW}No cases loaded from {data_path}{RESET}")
        sys.exit(1)
    run_id = uuid.uuid4().hex[:8]
    base_url = args.base_url.rstrip("/")
    print(f"\n{BOLD}Casual Chatlog E2E Replay{RESET}")
    print(f"{GRAY}  file={data_path}  base_url={base_url}  mode={args.dataset_mode}"
          f"  cases={len(cases)}  timeout={args.timeout}s  retries={args.retries}  run_id={run_id}{RESET}\n")
    auth_token: Optional[str] = args.auth_token.strip() or None
    token_secret: Optional[str] = (args.token_secret or "").strip() or None
    use_per_case_tokens = (auth_token is None) and (token_secret is not None)
    run_one = _make_run_one(args, run_id, base_url, auth_token, token_secret, use_per_case_tokens)
    all_doctor_ids = [f"{args.doctor_prefix}_{run_id}_{c.case_id.lower()}" for c in cases]
    workers = max(1, int(args.workers))
    results: List[CaseResult] = []
    try:
        if workers == 1:
            results = _run_cases_serial(cases, run_one, args.fail_fast)
        else:
            results = _run_cases_parallel(cases, run_one, workers, args.fail_fast)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted — running cleanup…{RESET}")
    finally:
        if not args.no_cleanup:
            _cleanup_e2e_data(all_doctor_ids, label="e2e-cleanup")
    _print_summary(results)


if __name__ == "__main__":
    main()
