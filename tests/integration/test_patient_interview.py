"""E2E test runner for patient interview benchmark.

Runs each case through the live server's patient interview API:
  /api/patient/register → /api/patient/interview/start → /turn × N → /confirm

Requires:
  - Running server on port 8001
  - Ollama on LAN
  - RUN_E2E_FIXTURES=1

Usage:
  PYTHONPATH=src ENVIRONMENT=development RUN_E2E_FIXTURES=1 \
    pytest tests/integration/test_patient_interview.py -v
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

from tests.integration.conftest import DB_PATH, SERVER

if os.environ.get("RUN_E2E_FIXTURES") != "1":
    pytest.skip(
        "Set RUN_E2E_FIXTURES=1 to run E2E fixture tests.",
        allow_module_level=True,
    )

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "patient_sim" / "scenarios"
TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)


def _load_cases() -> List[Dict[str, Any]]:
    if not FIXTURES_DIR.exists():
        return []
    cases = []
    for f in sorted(FIXTURES_DIR.glob("*.json")):
        cases.append(json.loads(f.read_text()))
    return cases


ALL_CASES = _load_cases()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _setup_doctor(doctor_id: str) -> None:
    """Ensure a doctor row exists."""
    from datetime import datetime
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO doctors (doctor_id, created_at, updated_at) "
            "VALUES (?, ?, ?)",
            (doctor_id, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def _register_patient(
    doctor_id: str, info: Dict[str, Any]
) -> Dict[str, Any]:
    """Register a patient and return {token, patient_id, patient_name}."""
    resp = httpx.post(
        f"{SERVER}/api/patient/register",
        json={
            "doctor_id": doctor_id,
            "name": info["name"],
            "gender": info.get("gender", ""),
            "year_of_birth": info["year_of_birth"],
            "phone": info["phone"],
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _start_interview(token: str) -> Dict[str, Any]:
    resp = httpx.post(
        f"{SERVER}/api/patient/interview/start",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _send_turn(token: str, session_id: str, text: str) -> Dict[str, Any]:
    resp = httpx.post(
        f"{SERVER}/api/patient/interview/turn",
        json={"session_id": session_id, "text": text},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _confirm(token: str, session_id: str) -> Dict[str, Any]:
    resp = httpx.post(
        f"{SERVER}/api/patient/interview/confirm",
        json={"session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _cancel(token: str, session_id: str) -> Dict[str, Any]:
    resp = httpx.post(
        f"{SERVER}/api/patient/interview/cancel",
        json={"session_id": session_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _login(phone: str, year_of_birth: int, doctor_id: Optional[str] = None) -> httpx.Response:
    payload: Dict[str, Any] = {"phone": phone, "year_of_birth": year_of_birth}
    if doctor_id:
        payload["doctor_id"] = doctor_id
    return httpx.post(
        f"{SERVER}/api/patient/login",
        json=payload,
        timeout=TIMEOUT,
    )


def _create_patient_direct(doctor_id: str, info: Dict[str, Any]) -> int:
    """Create a patient directly in DB (for pre_create_patient cases)."""
    from datetime import datetime
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            "INSERT INTO patients (doctor_id, name, gender, year_of_birth, created_at) VALUES (?, ?, ?, ?, ?)",
            (doctor_id, info["name"], info.get("gender"), info.get("year_of_birth"), now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


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


def _cleanup(doctor_id: str) -> None:
    """Remove all test data for this doctor."""
    conn = sqlite3.connect(DB_PATH)
    try:
        for table in [
            "interview_sessions", "medical_records", "doctor_tasks",
            "patients", "doctor_contexts", "doctor_chat_log",
            "doctor_conversation_turns",
        ]:
            try:
                conn.execute(f"DELETE FROM {table} WHERE doctor_id = ?", (doctor_id,))
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("DELETE FROM doctors WHERE doctor_id = ?", (doctor_id,))
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


def _contains_any(text: str, keywords: List[str]) -> bool:
    return any(kw in text for kw in keywords)


# ── Test cases ───────────────────────────────────────────────────────────────


def _run_full_flow(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run a standard interview flow: register → start → turns → check."""
    doctor_id = f"inttest_pi_{case['case_id'].lower()}_{uuid.uuid4().hex[:6]}"
    _setup_doctor(doctor_id)

    try:
        patient_info = case["patient_info"]
        reg = _register_patient(doctor_id, patient_info)
        token = reg["token"]

        start = _start_interview(token)
        session_id = start["session_id"]

        chatlog = case.get("chatlog", [])
        last_turn = None
        all_replies = [start.get("reply", "")]

        for turn in chatlog:
            if turn.get("speaker") != "patient":
                continue
            last_turn = _send_turn(token, session_id, turn["text"])
            all_replies.append(last_turn.get("reply", ""))

        return {
            "doctor_id": doctor_id,
            "token": token,
            "session_id": session_id,
            "last_turn": last_turn,
            "all_replies": all_replies,
            "patient_id": reg.get("patient_id"),
        }
    except Exception:
        _cleanup(doctor_id)
        raise


# Filter cases by group for parametrize
_FLOW_CASES = [c for c in ALL_CASES if c.get("chatlog") and c["case_id"] not in ("PI-005", "PI-006", "PI-007", "PI-008", "PI-009")]
_RESUME_CASES = [c for c in ALL_CASES if c["case_id"] == "PI-005"]
_CANCEL_CASES = [c for c in ALL_CASES if c["case_id"] == "PI-006"]
_REG_CASES = [c for c in ALL_CASES if c["case_id"] in ("PI-007", "PI-008")]
_AUTH_CASES = [c for c in ALL_CASES if c["case_id"] == "PI-009"]


@pytest.mark.integration
@pytest.mark.parametrize("case", _FLOW_CASES, ids=lambda c: c["case_id"])
def test_interview_flow(case: Dict[str, Any]):
    """Full interview flow: register → start → turns → assertions."""
    result = _run_full_flow(case)
    doctor_id = result["doctor_id"]
    expectations = case.get("expectations", {})

    try:
        last_turn = result["last_turn"]
        assert last_turn is not None, f"[{case['case_id']}] no turns sent"

        collected = last_turn.get("collected", {})
        status = last_turn.get("status", "")

        # min_fields_filled
        min_filled = expectations.get("min_fields_filled")
        if min_filled is not None:
            filled = sum(1 for v in collected.values() if v)
            assert filled >= min_filled, (
                f"[{case['case_id']}] expected >= {min_filled} fields filled, got {filled}. "
                f"Collected: {json.dumps(collected, ensure_ascii=False)[:300]}"
            )

        # required_fields_present
        for field in expectations.get("required_fields_present", []):
            assert field in collected and collected[field], (
                f"[{case['case_id']}] required field '{field}' missing or empty"
            )

        # chief_complaint_contains_any
        cc_keywords = expectations.get("chief_complaint_contains_any", [])
        if cc_keywords:
            cc = collected.get("chief_complaint", "")
            assert _contains_any(cc, cc_keywords), (
                f"[{case['case_id']}] chief_complaint missing keywords {cc_keywords}. Got: {cc}"
            )

        # past_history_contains_any
        ph_keywords = expectations.get("past_history_contains_any", [])
        if ph_keywords:
            ph = collected.get("past_history", "")
            assert _contains_any(ph, ph_keywords), (
                f"[{case['case_id']}] past_history missing keywords {ph_keywords}. Got: {ph}"
            )

        # allergy_history_contains_any
        ah_keywords = expectations.get("allergy_history_contains_any", [])
        if ah_keywords:
            ah = collected.get("allergy_history", "")
            assert _contains_any(ah, ah_keywords), (
                f"[{case['case_id']}] allergy_history missing keywords {ah_keywords}. Got: {ah}"
            )

        # final_status
        expected_status = expectations.get("final_status")
        if expected_status:
            assert status == expected_status, (
                f"[{case['case_id']}] expected status '{expected_status}', got '{status}'"
            )

        # confirm_creates_record
        if expectations.get("confirm_creates_record"):
            confirm_resp = _confirm(result["token"], result["session_id"])
            assert confirm_resp.get("status") == "confirmed", (
                f"[{case['case_id']}] confirm failed: {confirm_resp}"
            )
            assert confirm_resp.get("record_id") is not None, (
                f"[{case['case_id']}] confirm didn't return record_id"
            )

            # task_created
            if expectations.get("task_created"):
                assert confirm_resp.get("task_id") is not None, (
                    f"[{case['case_id']}] confirm didn't create task"
                )

            # record_content_contains_any
            rc_keywords = expectations.get("record_content_contains_any", [])
            if rc_keywords:
                conn = sqlite3.connect(DB_PATH)
                try:
                    row = conn.execute(
                        "SELECT content FROM medical_records WHERE id = ?",
                        (confirm_resp["record_id"],),
                    ).fetchone()
                    content = row[0] if row else ""
                    assert _contains_any(content, rc_keywords), (
                        f"[{case['case_id']}] record content missing {rc_keywords}. Got: {content[:200]}"
                    )
                finally:
                    conn.close()

    finally:
        _cleanup(doctor_id)


@pytest.mark.integration
@pytest.mark.parametrize("case", _RESUME_CASES, ids=lambda c: c["case_id"])
def test_interview_resume(case: Dict[str, Any]):
    """PI-005: Resume interrupted interview preserves collected data."""
    doctor_id = f"inttest_pi_{case['case_id'].lower()}_{uuid.uuid4().hex[:6]}"
    _setup_doctor(doctor_id)

    try:
        patient_info = case["patient_info"]
        reg = _register_patient(doctor_id, patient_info)
        token = reg["token"]

        # Part 1: start + first turns
        start = _start_interview(token)
        session_id = start["session_id"]
        for turn in case.get("chatlog_part1", []):
            _send_turn(token, session_id, turn["text"])

        # Resume: start again should return same session
        resume = _start_interview(token)
        assert resume.get("resumed") is True, f"[PI-005] expected resumed=True"
        assert resume["session_id"] == session_id, f"[PI-005] session_id changed on resume"

        # Part 2: continue with more turns
        last_turn = None
        for turn in case.get("chatlog_part2", []):
            last_turn = _send_turn(token, session_id, turn["text"])

        expectations = case.get("expectations", {})
        if expectations.get("confirm_creates_record") and last_turn:
            confirm_resp = _confirm(token, session_id)
            assert confirm_resp.get("status") == "confirmed"

    finally:
        _cleanup(doctor_id)


@pytest.mark.integration
@pytest.mark.parametrize("case", _CANCEL_CASES, ids=lambda c: c["case_id"])
def test_interview_cancel(case: Dict[str, Any]):
    """PI-006: Cancel then restart gives fresh session."""
    doctor_id = f"inttest_pi_{case['case_id'].lower()}_{uuid.uuid4().hex[:6]}"
    _setup_doctor(doctor_id)

    try:
        patient_info = case["patient_info"]
        reg = _register_patient(doctor_id, patient_info)
        token = reg["token"]

        # Start first session
        start1 = _start_interview(token)
        session_id1 = start1["session_id"]

        # Send a turn
        for turn in case.get("chatlog", []):
            _send_turn(token, session_id1, turn["text"])

        # Cancel
        _cancel(token, session_id1)

        # Start new session — should be different
        start2 = _start_interview(token)
        assert start2["session_id"] != session_id1, (
            f"[PI-006] new session should have different ID after cancel"
        )
        assert start2.get("resumed") is not True, (
            f"[PI-006] new session should not be resumed"
        )

    finally:
        _cleanup(doctor_id)


@pytest.mark.integration
@pytest.mark.parametrize("case", _REG_CASES, ids=lambda c: c["case_id"])
def test_registration(case: Dict[str, Any]):
    """PI-007/008: Registration links or rejects."""
    doctor_id = f"inttest_pi_{case['case_id'].lower()}_{uuid.uuid4().hex[:6]}"
    _setup_doctor(doctor_id)

    try:
        # Pre-create patient if needed
        pre = case.get("pre_create_patient")
        if pre:
            _create_patient_direct(doctor_id, pre)

        reg_input = case["register_input"]
        expectations = case.get("expectations", {})

        if expectations.get("register_rejected"):
            resp = httpx.post(
                f"{SERVER}/api/patient/register",
                json={
                    "doctor_id": doctor_id,
                    "name": reg_input["name"],
                    "gender": reg_input.get("gender", ""),
                    "year_of_birth": reg_input["year_of_birth"],
                    "phone": reg_input["phone"],
                },
                timeout=TIMEOUT,
            )
            assert resp.status_code >= 400, (
                f"[{case['case_id']}] expected registration rejection, got {resp.status_code}"
            )
            if expectations.get("reject_reason_contains"):
                assert expectations["reject_reason_contains"] in resp.text, (
                    f"[{case['case_id']}] rejection reason missing '{expectations['reject_reason_contains']}': {resp.text}"
                )
        else:
            reg = _register_patient(doctor_id, reg_input)

            if expectations.get("links_to_existing"):
                # Should have only 1 patient (linked, not duplicated)
                count = _db_count(doctor_id, "patients")
                assert count == 1, (
                    f"[{case['case_id']}] expected 1 patient (linked), got {count}"
                )

            if expectations.get("backfills_phone"):
                conn = sqlite3.connect(DB_PATH)
                try:
                    row = conn.execute(
                        "SELECT phone FROM patients WHERE id = ?",
                        (reg["patient_id"],),
                    ).fetchone()
                    assert row and row[0] == reg_input["phone"], (
                        f"[{case['case_id']}] phone not backfilled"
                    )
                finally:
                    conn.close()

    finally:
        _cleanup(doctor_id)


@pytest.mark.integration
@pytest.mark.parametrize("case", _AUTH_CASES, ids=lambda c: c["case_id"])
def test_auth(case: Dict[str, Any]):
    """PI-009: Wrong YOB login rejected."""
    doctor_id = f"inttest_pi_{case['case_id'].lower()}_{uuid.uuid4().hex[:6]}"
    _setup_doctor(doctor_id)

    try:
        # First register the patient
        patient_info = case["patient_info"]
        _register_patient(doctor_id, patient_info)

        # Then try login with wrong credentials
        login_with = case["login_with"]
        resp = _login(login_with["phone"], login_with["year_of_birth"], doctor_id)

        expectations = case.get("expectations", {})
        if expectations.get("login_rejected"):
            assert resp.status_code >= 400, (
                f"[{case['case_id']}] expected login rejection, got {resp.status_code}: {resp.text}"
            )

    finally:
        _cleanup(doctor_id)
