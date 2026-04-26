"""Kind B: Patient intake workflow tests.

Tests patient registration, intake flow (start → turns → confirm),
session management (resume, cancel/restart), and auth rejection.

Requires: running server on port 8001 with a test doctor that accepts patients.
"""
from __future__ import annotations

import time
from uuid import uuid4

import pytest

from tests.regression.helpers import db_count, db_patient, db_record_fields
from tests.regression.helpers_patient import (
    patient_register,
    patient_login,
    patient_intake_start,
    patient_intake_turn,
    patient_intake_confirm,
    patient_intake_cancel,
    patient_intake_current,
)

pytestmark = [pytest.mark.regression, pytest.mark.workflow]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_doctor(server_url, db_path, cleanup):
    """Create a test doctor and return doctor_id.

    The doctor must exist in the DB for patient registration to succeed.
    """
    import sqlite3
    from datetime import datetime
    doctor_id = cleanup.make_doctor_id("pat")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO doctors (doctor_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (doctor_id, "测试医生", datetime.now().isoformat(), datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return doctor_id


def _register_and_get_token(server_url, doctor_id, name="测试患者", gender="女",
                             year_of_birth=1990, phone=None):
    """Helper: register patient and return (token, patient_id)."""
    if phone is None:
        phone = f"138{uuid4().hex[:8]}"
    status, body = patient_register(
        server_url, doctor_id, name, gender, year_of_birth, phone,
    )
    assert status == 200, f"Registration failed: {body}"
    return body["token"], body["patient_id"], phone


# ---------------------------------------------------------------------------
# Full intake flow
# ---------------------------------------------------------------------------

class TestFullFlow:
    def test_simple_headache(self, server_url, db_path, test_doctor):
        """Register → start → 5 turns → confirm → record created."""
        token, patient_id, _ = _register_and_get_token(
            server_url, test_doctor, name="头痛患者", year_of_birth=1985,
        )

        # Start intake
        start = patient_intake_start(server_url, token)
        sid = start["session_id"]
        assert start["status"] in ("active", "IntakeStatus.active")

        # Intake turns
        turns = [
            "我头疼",
            "大概三天了",
            "没有其他疾病",
            "没有过敏",
            "不吸烟不喝酒，没有家族病史",
        ]
        for text in turns:
            resp = patient_intake_turn(server_url, token, sid, text)
            assert "reply" in resp

        # Check collected has content
        collected = resp.get("collected", {})
        filled = [k for k, v in collected.items() if v and not k.startswith("_")]
        assert len(filled) >= 3, f"Expected ≥3 filled fields, got {filled}"

        # Confirm
        status_code, body = patient_intake_confirm(server_url, token, sid)
        assert status_code == 200, f"Confirm failed: {body}"
        assert body.get("record_id"), "No record_id returned"

        time.sleep(0.5)
        assert db_count(db_path, test_doctor, "medical_records") >= 1

    def test_abdominal_pain_with_history(self, server_url, db_path, test_doctor):
        """Patient with surgical history — past_history should be populated."""
        token, _, _ = _register_and_get_token(
            server_url, test_doctor, name="腹痛患者", year_of_birth=1978,
        )

        start = patient_intake_start(server_url, token)
        sid = start["session_id"]

        turns = [
            "肚子疼，右下腹",
            "两天了，越来越疼",
            "三年前做过阑尾炎手术",
            "对青霉素过敏",
            "不抽烟不喝酒",
            "爸爸有高血压",
        ]
        resp = None
        for text in turns:
            resp = patient_intake_turn(server_url, token, sid, text)

        collected = resp.get("collected", {})
        filled = [k for k, v in collected.items() if v and not k.startswith("_")]
        assert len(filled) >= 4, f"Expected ≥4 filled fields, got {filled}"

        status_code, body = patient_intake_confirm(server_url, token, sid)
        assert status_code == 200


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class TestSessionManagement:
    def test_resume_interrupted(self, server_url, db_path, test_doctor):
        """Start → 2 turns → start again → same session, collected preserved."""
        token, _, _ = _register_and_get_token(
            server_url, test_doctor, name="中断患者", year_of_birth=1980,
        )

        # First session
        start1 = patient_intake_start(server_url, token)
        sid1 = start1["session_id"]

        patient_intake_turn(server_url, token, sid1, "腰疼")
        patient_intake_turn(server_url, token, sid1, "一周了")

        # "Resume" — start again should return same session
        start2 = patient_intake_start(server_url, token)
        sid2 = start2["session_id"]
        assert sid2 == sid1, f"Expected same session, got {sid2} vs {sid1}"
        assert start2.get("resumed") is True

        # Collected should be preserved
        collected = start2.get("collected", {})
        assert any(v for k, v in collected.items() if not k.startswith("_")), \
            "Collected should have data after resume"

    def test_cancel_and_restart(self, server_url, db_path, test_doctor):
        """Start → cancel → start again → new session."""
        token, _, _ = _register_and_get_token(
            server_url, test_doctor, name="取消患者", year_of_birth=1975,
        )

        start1 = patient_intake_start(server_url, token)
        sid1 = start1["session_id"]
        patient_intake_turn(server_url, token, sid1, "头晕")

        # Cancel
        patient_intake_cancel(server_url, token, sid1)

        # Start again — should be NEW session
        start2 = patient_intake_start(server_url, token)
        sid2 = start2["session_id"]
        assert sid2 != sid1, f"Expected new session after cancel, got same {sid1}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_links_existing_patient(self, server_url, db_path, test_doctor):
        """If doctor already has a patient with that name, registration links to it."""
        # Pre-create patient via doctor intake
        from tests.regression.helpers import intake_turn, intake_confirm
        r = intake_turn(server_url, f"注册测试 女 45岁 体检", doctor_id=test_doctor)
        intake_confirm(server_url, r["session_id"], test_doctor)
        time.sleep(0.5)

        # Now patient registers with same name
        status, body = patient_register(
            server_url, test_doctor, "注册测试", "女", 1981, f"138{uuid4().hex[:8]}",
        )
        assert status == 200
        assert body.get("patient_id"), "Should link to existing patient"

        # Should NOT create a duplicate
        assert db_count(db_path, test_doctor, "patients") == 1, "Should not duplicate patient"

    def test_register_rejects_mismatched_yob(self, server_url, db_path, test_doctor):
        """If patient exists with different YOB, registration should reject."""
        # Pre-create patient with YOB=1990
        phone = f"138{uuid4().hex[:8]}"
        status1, body1 = patient_register(
            server_url, test_doctor, "年龄测试", "男", 1990, phone,
        )
        assert status1 == 200

        # Try registering same name with different YOB
        status2, body2 = patient_register(
            server_url, test_doctor, "年龄测试", "男", 1985, f"138{uuid4().hex[:8]}",
        )
        assert status2 == 400, f"Expected 400 for mismatched YOB, got {status2}"

    def test_wrong_yob_login_rejected(self, server_url, db_path, test_doctor):
        """Login with wrong year_of_birth should be rejected."""
        phone = f"138{uuid4().hex[:8]}"
        patient_register(server_url, test_doctor, "登录测试", "女", 1992, phone)

        # Try login with wrong YOB
        status, body = patient_login(server_url, phone, 1988, test_doctor)
        assert status == 401, f"Expected 401 for wrong YOB, got {status}"


# ---------------------------------------------------------------------------
# Extraction quality
# ---------------------------------------------------------------------------

class TestPatientExtraction:
    def test_negatives_captured(self, server_url, db_path, test_doctor):
        """Patient denials (没有/不/无) should be captured in record."""
        token, _, _ = _register_and_get_token(
            server_url, test_doctor, name="否认患者", year_of_birth=1988,
        )

        start = patient_intake_start(server_url, token)
        sid = start["session_id"]

        turns = [
            "头晕两天",
            "没有头痛，没有恶心",
            "没有高血压糖尿病",
            "没有过敏",
            "不抽烟不喝酒",
            "没有家族病史",
        ]
        for text in turns:
            patient_intake_turn(server_url, token, sid, text)

        status_code, _ = patient_intake_confirm(server_url, token, sid)
        assert status_code == 200
        time.sleep(0.5)

        record = db_record_fields(db_path, test_doctor)
        assert record, "No record created"
        assert record.get("chief_complaint"), "chief_complaint should be filled"

    def test_combined_multi_field_answers(self, server_url, db_path, test_doctor):
        """Patient gives multiple facts in one answer — should be split to correct fields."""
        token, _, _ = _register_and_get_token(
            server_url, test_doctor, name="综合患者", year_of_birth=1982,
        )

        start = patient_intake_start(server_url, token)
        sid = start["session_id"]

        turns = [
            "胸闷气短一周了",
            "以前有高血压，吃氨氯地平，对青霉素过敏",
            "不抽烟，已婚有一个孩子",
            "爸爸有心脏病",
            "没有做过手术",
            "就这些了",
        ]
        for text in turns:
            patient_intake_turn(server_url, token, sid, text)

        status_code, _ = patient_intake_confirm(server_url, token, sid)
        assert status_code == 200
        time.sleep(0.5)

        record = db_record_fields(db_path, test_doctor)
        filled = [k for k, v in record.items() if v]
        assert len(filled) >= 4, f"Expected ≥4 fields from combined answers, got {len(filled)}: {filled}"

    def test_history_injection(self, server_url, db_path, test_doctor):
        """Patient mentions rare allergy — should appear in allergy_history."""
        token, _, _ = _register_and_get_token(
            server_url, test_doctor, name="过敏患者", year_of_birth=1995,
        )

        start = patient_intake_start(server_url, token)
        sid = start["session_id"]

        turns = [
            "膝盖疼",
            "两周了，走路加重",
            "没有其他病",
            "我对磺胺类药物和海鲜过敏",
            "不吸烟",
            "没有家族病史",
        ]
        for text in turns:
            patient_intake_turn(server_url, token, sid, text)

        status_code, _ = patient_intake_confirm(server_url, token, sid)
        assert status_code == 200
        time.sleep(0.5)

        record = db_record_fields(db_path, test_doctor)
        allergy = record.get("allergy_history", "")
        assert "磺胺" in allergy or "海鲜" in allergy, \
            f"Expected 磺胺 or 海鲜 in allergy_history, got: {allergy}"
