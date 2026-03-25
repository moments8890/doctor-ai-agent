"""Unified E2E test runner for all fixture files.

Updated for Plan-and-Act architecture (2026-03):
- create_record intent now starts an interview session (not one-shot record)
- "confirm" turns are skipped (no pending_records pipeline)
- medical_records min-count assertions replaced with interview_sessions
- Groups that depend on record mutation (update_record, correction) are skipped

Runs each case through the live server, verifying:
- Patient creation and dedup
- Interview session creation (for create_save group)
- Reply text keywords
- Table row counts (patients, interview_sessions, doctor_tasks)

How to run:
  1) Start server: cd src && uvicorn main:app --port 8000
  2) INTEGRATION_SERVER_URL=http://127.0.0.1:8000 RUN_E2E_FIXTURES=1 \
     pytest tests/integration/test_e2e_fixtures.py -v

Requires: running server, LLM backend.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pytest

from tests.integration.conftest import DB_PATH, SERVER, chat


if os.environ.get("RUN_E2E_FIXTURES") != "1":
    pytest.skip(
        "Set RUN_E2E_FIXTURES=1 to run E2E fixture tests.",
        allow_module_level=True,
    )


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "doctor_sim" / "scenarios"

# Load all individual scenario JSON files (previously one monolithic benchmark file)
FIXTURE_FILES = []  # now loaded individually from scenarios/

# ── Groups that must be skipped in Plan-and-Act ───────────────────────────
_SKIP_GROUPS: Dict[str, str] = {
    "update_record": "update_record removed -- UI-only in Plan-and-Act",
    "correction": "correction requires update_record -- not supported in Plan-and-Act",
    "compound_record_task": "multi-intent compound actions not supported in Plan-and-Act",
    "schedule": "auto-schedule from chat removed in Plan-and-Act",
}

# In Plan-and-Act, create_record starts an interview session instead of
# writing directly to medical_records.  For any min-count check on
# medical_records, we substitute interview_sessions instead.  Max-count
# checks of 0 (asserting nothing was created) are kept on medical_records.

# ── Groups where all assertions are relaxed to "reply is non-empty" ───────
_RELAXED_GROUPS = {
    "query_history",
    "query_only",
}

# ── "Confirm" turns that should be skipped (old pending_records flow) ─────
_CONFIRM_TEXTS = {"确认", "确认保存", "保存"}


def _load_all_cases() -> List[Dict[str, Any]]:
    cases = []
    if not FIXTURES_DIR.exists():
        return cases
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        case["_source_file"] = path.name
        cases.append(case)
    return cases


# ── DB helpers ────────────────────────────────────────────────────────────

def _db_count(doctor_id: str, table: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE doctor_id = ?", (doctor_id,)
        ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _db_patient(doctor_id: str, name: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM patients WHERE doctor_id = ? AND name = ? ORDER BY id DESC LIMIT 1",
            (doctor_id, name),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _db_interview_session(doctor_id: str) -> Optional[Dict]:
    """Get latest interview session for doctor."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM interview_sessions WHERE doctor_id = ? ORDER BY created_at DESC LIMIT 1",
            (doctor_id,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None  # table may not exist
    finally:
        conn.close()


def _db_latest_record_content(doctor_id: str) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT content FROM medical_records WHERE doctor_id = ? ORDER BY id DESC LIMIT 1",
            (doctor_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _contains_any(text: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    return any(k in text for k in keywords)


def _is_confirm_turn(text: str) -> bool:
    """Check if a turn text is a bare confirm command (old pending_records flow)."""
    return text.strip() in _CONFIRM_TEXTS


# ── Interview API helpers ─────────────────────────────────────────────────

def interview_turn(session_id: str, text: str, doctor_id: str, server_url: str = SERVER):
    """Call /api/records/interview/turn with Form data."""
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
    resp = httpx.post(
        f"{server_url}/api/records/interview/turn",
        data={"session_id": session_id, "text": text, "doctor_id": doctor_id},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def interview_confirm(session_id: str, doctor_id: str, server_url: str = SERVER):
    """Call /api/records/interview/confirm with Form data."""
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
    resp = httpx.post(
        f"{server_url}/api/records/interview/confirm",
        data={"session_id": session_id, "doctor_id": doctor_id},
        timeout=timeout,
    )
    # Don't raise -- confirm may fail if pending_records pipeline is broken
    try:
        body = resp.json() if resp.status_code == 200 else {}
    except Exception:
        body = {}
    return resp.status_code, body


ALL_CASES = _load_all_cases()

_CLEANUP_TABLES = [
    "patient_auth", "interview_sessions", "medical_records",
    "doctor_tasks", "doctor_chat_log",
    "doctor_conversation_turns", "doctor_contexts", "doctor_session_states",
    "patients", "doctors",
]


def _cleanup_doctor(doctor_id: str) -> None:
    """Delete all data for a test doctor_id after a test run."""
    conn = sqlite3.connect(DB_PATH)
    try:
        for table in _CLEANUP_TABLES:
            try:
                conn.execute(f"DELETE FROM {table} WHERE doctor_id = ?", (doctor_id,))
            except sqlite3.OperationalError:
                pass  # table may not exist or no doctor_id column
        conn.commit()
    finally:
        conn.close()


@pytest.mark.integration
@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c["case_id"])
def test_e2e_fixture(case: Dict[str, Any]):
    group = case.get("group", "")
    case_id = case["case_id"]
    doctor_id = f"inttest_{case_id.lower()}_{uuid.uuid4().hex[:6]}"
    chatlog = case.get("chatlog", [])
    expectations = case.get("expectations", {})

    # ── Skip groups not supported in Plan-and-Act ─────────────────────
    if group in _SKIP_GROUPS:
        pytest.skip(_SKIP_GROUPS[group])

    # ── Send turns ────────────────────────────────────────────────────
    all_replies: List[str] = []
    last_data: Optional[Dict] = None

    for turn in chatlog:
        if turn.get("speaker") != "doctor":
            continue
        text = turn["text"]

        # Skip bare "confirm" turns -- the old pending_records two-step
        # flow is dead.  In Plan-and-Act the first chat turn starts an
        # interview session; there is nothing to confirm via /chat.
        if _is_confirm_turn(text):
            continue

        data = chat(text, doctor_id=doctor_id)
        all_replies.append(data.get("reply", ""))
        last_data = data

    joined_reply = "\n".join(all_replies)

    # ── For create_save: try to confirm the interview session ─────────
    # The chat turn starts an interview session. To get a medical_record
    # in the DB, we need to confirm the session via the interview API.
    if group == "create_save":
        session_row = _db_interview_session(doctor_id)
        if session_row:
            session_id = session_row["id"]
            status_code, confirm_body = interview_confirm(session_id, doctor_id)
            if status_code == 200:
                all_replies.append(f"[confirm] {confirm_body.get('status', '')}")
            joined_reply = "\n".join(all_replies)

    # ── Relaxed groups: just check we got a non-empty reply ───────────
    if group in _RELAXED_GROUPS:
        # For query_history and query_only, the prerequisite record
        # doesn't exist in Plan-and-Act (interview doesn't auto-save).
        # We still assert patient creation and non-empty reply.
        expected_name = expectations.get("expected_patient_name")
        if expected_name:
            patient = _db_patient(doctor_id, expected_name)
            assert patient is not None, (
                f"[{case_id}] expected patient '{expected_name}' not found in DB"
            )
        assert joined_reply.strip(), (
            f"[{case_id}] expected non-empty reply, got empty"
        )
        _cleanup_doctor(doctor_id)
        return

    # ── Assert: must_not_timeout (implicit -- chat() raises on timeout)

    # ── Assert: expected_patient_name ─────────────────────────────────
    expected_name = expectations.get("expected_patient_name")
    if expected_name:
        patient = _db_patient(doctor_id, expected_name)
        assert patient is not None, (
            f"[{case_id}] expected patient '{expected_name}' not found in DB"
        )

    # ── Assert: expected_patient_count ────────────────────────────────
    expected_count = expectations.get("expected_patient_count")
    if expected_count is not None:
        actual = _db_count(doctor_id, "patients")
        assert actual == expected_count, (
            f"[{case_id}] expected {expected_count} patients, got {actual}"
        )

    # ── Assert: table min counts ─────────────────────────────────────
    min_counts = expectations.get("expected_table_min_counts_by_doctor", {})
    for table, min_val in min_counts.items():
        if table == "medical_records":
            # In Plan-and-Act, create_record starts an interview session
            # and confirm creates the medical_record. Check either table.
            records_count = _db_count(doctor_id, "medical_records")
            sessions_count = _db_count(doctor_id, "interview_sessions")
            total = records_count + sessions_count
            assert total >= min_val, (
                f"[{case_id}] medical_records({records_count}) + "
                f"interview_sessions({sessions_count}) = {total}, expected >= {min_val}"
            )
            continue
        actual = _db_count(doctor_id, table)
        assert actual >= min_val, (
            f"[{case_id}] {table}: expected >= {min_val}, got {actual}"
        )

    # ── Assert: table max counts ──────────────────────────────────────
    # Keep medical_records max-0 checks (asserting nothing was created)
    # but skip max checks for medical_records where min > 0 was expected
    # (the new flow creates interview_sessions, not records).
    max_counts = expectations.get("expected_table_max_counts_by_doctor", {})
    for table, max_val in max_counts.items():
        if table == "medical_records" and min_counts.get("medical_records", 0) > 0:
            # This case expected records to be created (old flow).
            # In Plan-and-Act records are not created, skip this check.
            continue
        actual = _db_count(doctor_id, table)
        assert actual <= max_val, (
            f"[{case_id}] {table}: expected <= {max_val}, got {actual}"
        )

    # ── Assert: interview session has collected data ──────────────────
    if min_counts.get("medical_records", 0) > 0:
        session = _db_interview_session(doctor_id)
        assert session is not None, (
            f"[{case_id}] expected interview_sessions row for doctor, found none"
        )
        # If session has collected data, verify it's non-empty JSON
        collected = session.get("collected")
        if collected:
            try:
                collected_dict = json.loads(collected)
                assert isinstance(collected_dict, dict), (
                    f"[{case_id}] interview collected should be dict, got {type(collected_dict)}"
                )
            except json.JSONDecodeError:
                pass  # collected may be empty or malformed early in flow

    # ── Assert: must_include_any_of (record content keywords) ─────────
    # In Plan-and-Act, records may not be created; check interview
    # collected data instead of medical_records content.
    must_include = expectations.get("must_include_any_of", [])
    if must_include:
        if min_counts.get("medical_records", 0) > 0:
            session = _db_interview_session(doctor_id)
            content = session.get("collected", "") if session else ""
            for keyword_group in must_include:
                assert _contains_any(content, keyword_group), (
                    f"[{case_id}] interview collected missing keywords from {keyword_group}. "
                    f"Collected: {content[:200]}"
                )
        else:
            content = _db_latest_record_content(doctor_id) or ""
            for keyword_group in must_include:
                assert _contains_any(content, keyword_group), (
                    f"[{case_id}] record content missing keywords from {keyword_group}. "
                    f"Content: {content[:200]}"
                )

    # ── Assert: must_include_reply_any_of (reply text keywords) ───────
    must_reply = expectations.get("must_include_reply_any_of", [])
    for keyword_group in must_reply:
        assert _contains_any(joined_reply, keyword_group), (
            f"[{case_id}] reply missing keywords from {keyword_group}. "
            f"Reply: {joined_reply[:300]}"
        )

    # ── Cleanup test data ─────────────────────────────────────────────
    _cleanup_doctor(doctor_id)
