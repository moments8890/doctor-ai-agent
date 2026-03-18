"""患者预问诊端到端集成测试。

End-to-end tests for the patient pre-consultation interview pipeline (ADR 0016).

These tests exercise the full flow:
  patient register → login → start interview → multi-turn Q&A → confirm → DB verify.

Assertions are DB-backed to validate persistence, not only API payloads.

Requires: running server at :8001 + Ollama on LAN (auto-skipped otherwise).
A doctor with accepting_patients=1 must exist (test creates one if missing).
"""

import json
import sqlite3
import uuid

import httpx
import pytest

from tests.integration.conftest import DB_PATH, SERVER

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


def _ensure_test_doctor(doctor_id: str) -> None:
    """Ensure a test doctor exists with accepting_patients=1."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT 1 FROM doctors WHERE doctor_id=?", (doctor_id,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO doctors (doctor_id, name, channel, accepting_patients, department) "
                "VALUES (?, ?, 'app', 1, '测试科')",
                (doctor_id, f"测试医生_{doctor_id[-4:]}"),
            )
        else:
            conn.execute(
                "UPDATE doctors SET accepting_patients=1, department='测试科' WHERE doctor_id=?",
                (doctor_id,),
            )
        conn.commit()
    finally:
        conn.close()


def _patient_api(method, path, token=None, json_body=None):
    """Call a patient API endpoint."""
    headers = {}
    if token:
        headers["X-Patient-Token"] = token
    if method == "GET":
        resp = httpx.get(f"{SERVER}{path}", headers=headers, timeout=_TIMEOUT)
    else:
        resp = httpx.post(
            f"{SERVER}{path}",
            json=json_body or {},
            headers=headers,
            timeout=_TIMEOUT,
        )
    return resp


def _db_query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _db_query_all(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _cleanup_patient(doctor_id, patient_name):
    """Remove test patient and related data."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM patients WHERE doctor_id=? AND name=?",
            (doctor_id, patient_name),
        ).fetchone()
        if row:
            pid = row[0]
            conn.execute("DELETE FROM interview_sessions WHERE patient_id=?", (pid,))
            conn.execute("DELETE FROM medical_records WHERE patient_id=?", (pid,))
            conn.execute("DELETE FROM doctor_tasks WHERE patient_id=?", (pid,))
            conn.execute("DELETE FROM patients WHERE id=?", (pid,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_doctor():
    """Return a unique test doctor_id, ensuring it exists with accepting_patients=1."""
    doctor_id = f"inttest_interview_{uuid.uuid4().hex[:6]}"
    _ensure_test_doctor(doctor_id)
    yield doctor_id


@pytest.fixture()
def registered_patient(test_doctor):
    """Register a test patient and return (token, patient_name, doctor_id)."""
    name = f"测试患者_{uuid.uuid4().hex[:4]}"
    resp = _patient_api("POST", "/api/patient/register", json_body={
        "doctor_id": test_doctor,
        "name": name,
        "gender": "男",
        "year_of_birth": 1990,
        "phone": f"138{uuid.uuid4().hex[:8]}",
    })
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    data = resp.json()
    yield data["token"], name, test_doctor
    _cleanup_patient(test_doctor, name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPatientRegistration:

    def test_register_new_patient(self, test_doctor):
        """New patient registration creates a patient row."""
        name = f"注册测试_{uuid.uuid4().hex[:4]}"
        phone = f"139{uuid.uuid4().hex[:8]}"

        resp = _patient_api("POST", "/api/patient/register", json_body={
            "doctor_id": test_doctor,
            "name": name,
            "gender": "女",
            "year_of_birth": 1985,
            "phone": phone,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["token"]
        assert data["patient_name"] == name

        # Verify in DB
        row = _db_query(
            "SELECT name, gender, year_of_birth, phone FROM patients WHERE doctor_id=? AND name=?",
            (test_doctor, name),
        )
        assert row is not None, "Patient row not created"
        assert row[0] == name
        assert row[1] == "女"
        assert row[2] == 1985
        assert row[3] == phone

        _cleanup_patient(test_doctor, name)

    def test_register_links_existing_patient(self, test_doctor):
        """Registration with matching name links to doctor-created patient."""
        name = f"已有患者_{uuid.uuid4().hex[:4]}"

        # Doctor creates patient first (simulate via direct DB insert)
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO patients (doctor_id, name, gender, year_of_birth) VALUES (?, ?, '男', 1975)",
            (test_doctor, name),
        )
        conn.commit()
        conn.close()

        # Patient registers with same name + backfills phone
        phone = f"137{uuid.uuid4().hex[:8]}"
        resp = _patient_api("POST", "/api/patient/register", json_body={
            "doctor_id": test_doctor,
            "name": name,
            "gender": "男",
            "year_of_birth": 1975,
            "phone": phone,
        })
        assert resp.status_code == 200

        # Verify phone was backfilled
        row = _db_query(
            "SELECT phone FROM patients WHERE doctor_id=? AND name=?",
            (test_doctor, name),
        )
        assert row[0] == phone

        # Verify no duplicate
        count = _db_query(
            "SELECT COUNT(1) FROM patients WHERE doctor_id=? AND name=?",
            (test_doctor, name),
        )
        assert count[0] == 1

        _cleanup_patient(test_doctor, name)

    def test_register_conflict_rejects(self, test_doctor):
        """Registration with mismatched YOB is rejected."""
        name = f"冲突测试_{uuid.uuid4().hex[:4]}"

        # Create patient with YOB 1980
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO patients (doctor_id, name, year_of_birth) VALUES (?, ?, 1980)",
            (test_doctor, name),
        )
        conn.commit()
        conn.close()

        # Register with different YOB
        resp = _patient_api("POST", "/api/patient/register", json_body={
            "doctor_id": test_doctor,
            "name": name,
            "gender": "男",
            "year_of_birth": 1990,
            "phone": "13800000000",
        })
        assert resp.status_code == 400
        assert "不符" in resp.json().get("detail", "")

        _cleanup_patient(test_doctor, name)


@pytest.mark.integration
class TestPatientLogin:

    def test_login_by_phone(self, test_doctor):
        """Login with phone + year_of_birth returns token."""
        name = f"登录测试_{uuid.uuid4().hex[:4]}"
        phone = f"136{uuid.uuid4().hex[:8]}"

        # Register first
        _patient_api("POST", "/api/patient/register", json_body={
            "doctor_id": test_doctor,
            "name": name,
            "gender": "男",
            "year_of_birth": 1992,
            "phone": phone,
        })

        # Login
        resp = _patient_api("POST", "/api/patient/login", json_body={
            "phone": phone,
            "year_of_birth": 1992,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["token"]
        assert data["patient_name"] == name

        _cleanup_patient(test_doctor, name)

    def test_login_wrong_yob_rejected(self, test_doctor):
        """Wrong year_of_birth is rejected."""
        name = f"错误登录_{uuid.uuid4().hex[:4]}"
        phone = f"135{uuid.uuid4().hex[:8]}"

        _patient_api("POST", "/api/patient/register", json_body={
            "doctor_id": test_doctor,
            "name": name,
            "gender": "女",
            "year_of_birth": 1988,
            "phone": phone,
        })

        resp = _patient_api("POST", "/api/patient/login", json_body={
            "phone": phone,
            "year_of_birth": 1999,
        })
        assert resp.status_code == 401

        _cleanup_patient(test_doctor, name)


@pytest.mark.integration
class TestDoctorSearch:

    def test_list_accepting_doctors(self, test_doctor):
        """Doctors with accepting_patients=1 appear in list."""
        resp = _patient_api("GET", "/api/patient/doctors")
        assert resp.status_code == 200
        doctors = resp.json()
        ids = [d["doctor_id"] for d in doctors]
        assert test_doctor in ids


@pytest.mark.integration
class TestInterviewSession:

    def test_start_creates_session(self, registered_patient):
        """Starting an interview creates a session in the DB."""
        token, name, doctor_id = registered_patient

        resp = _patient_api("POST", "/api/patient/interview/start", token=token)
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]
        assert data["status"] == "interviewing"
        assert data["progress"]["filled"] == 0
        assert "不舒服" in data["reply"] or "预问诊" in data["reply"]

    def test_resume_existing_session(self, registered_patient):
        """Starting twice returns the same session (resume)."""
        token, name, doctor_id = registered_patient

        resp1 = _patient_api("POST", "/api/patient/interview/start", token=token)
        sid1 = resp1.json()["session_id"]

        resp2 = _patient_api("POST", "/api/patient/interview/start", token=token)
        sid2 = resp2.json()["session_id"]
        assert sid2 == sid1
        assert resp2.json().get("resumed") is True

    def test_cancel_then_start_fresh(self, registered_patient):
        """Cancelling then starting gives a new session."""
        token, name, doctor_id = registered_patient

        resp1 = _patient_api("POST", "/api/patient/interview/start", token=token)
        sid1 = resp1.json()["session_id"]

        _patient_api("POST", "/api/patient/interview/cancel", token=token, json_body={"session_id": sid1})

        resp2 = _patient_api("POST", "/api/patient/interview/start", token=token)
        sid2 = resp2.json()["session_id"]
        assert sid2 != sid1


@pytest.mark.integration
class TestInterviewTurn:

    def test_single_turn_extracts_chief_complaint(self, registered_patient):
        """First turn with symptom should extract chief_complaint."""
        token, name, doctor_id = registered_patient

        start = _patient_api("POST", "/api/patient/interview/start", token=token)
        sid = start.json()["session_id"]

        resp = _patient_api("POST", "/api/patient/interview/turn", token=token, json_body={
            "session_id": sid,
            "text": "我头疼三天了",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"]  # AI should ask a follow-up
        assert data["progress"]["filled"] >= 1
        # chief_complaint should be extracted
        collected = data.get("collected", {})
        assert collected.get("chief_complaint"), f"chief_complaint not extracted: {collected}"

    def test_empty_text_rejected(self, registered_patient):
        """Empty message is rejected with 400."""
        token, name, doctor_id = registered_patient

        start = _patient_api("POST", "/api/patient/interview/start", token=token)
        sid = start.json()["session_id"]

        resp = _patient_api("POST", "/api/patient/interview/turn", token=token, json_body={
            "session_id": sid,
            "text": "  ",
        })
        assert resp.status_code == 400


@pytest.mark.integration
class TestInterviewFullFlow:

    def test_complete_interview_creates_record_and_task(self, registered_patient):
        """Full interview → confirm → medical record + doctor task in DB."""
        token, name, doctor_id = registered_patient

        # Start
        start = _patient_api("POST", "/api/patient/interview/start", token=token)
        sid = start.json()["session_id"]

        # Simulate multi-turn interview
        turns = [
            "我头痛三天了，持续性的",
            "以前做过阑尾手术",
            "没有药物过敏",
            "家人没有类似疾病",
            "不吸烟不饮酒",
        ]
        last_data = None
        for text in turns:
            resp = _patient_api("POST", "/api/patient/interview/turn", token=token, json_body={
                "session_id": sid,
                "text": text,
            })
            assert resp.status_code == 200
            last_data = resp.json()

        # Check progress — should have most fields filled
        filled = last_data["progress"]["filled"]
        assert filled >= 4, f"Expected at least 4 fields filled, got {filled}. Collected: {last_data.get('collected')}"

        # Confirm (even if not all fields, confirm should work from interviewing or reviewing)
        resp = _patient_api("POST", "/api/patient/interview/confirm", token=token, json_body={
            "session_id": sid,
        })
        assert resp.status_code == 200
        confirm_data = resp.json()
        assert confirm_data["status"] == "confirmed"
        assert confirm_data["record_id"]
        assert confirm_data["task_id"]

        # Verify medical record in DB
        record = _db_query(
            "SELECT content, record_type, needs_review, structured FROM medical_records WHERE id=?",
            (confirm_data["record_id"],),
        )
        assert record is not None, "Medical record not found in DB"
        assert record[1] == "interview_summary"
        assert record[2] == 1  # needs_review = true
        assert "头痛" in (record[0] or ""), f"Content missing symptom: {record[0]}"

        # Verify structured field is populated
        if record[3]:
            structured = json.loads(record[3])
            assert structured.get("chief_complaint"), f"Structured missing chief_complaint: {structured}"

        # Verify doctor task in DB
        task = _db_query(
            "SELECT title, task_type, status FROM doctor_tasks WHERE id=?",
            (confirm_data["task_id"],),
        )
        assert task is not None, "Doctor task not found in DB"
        assert "预问诊" in task[0]
        assert task[1] == "general"
        assert task[2] == "pending"

        # Verify session status is confirmed
        session = _db_query(
            "SELECT status FROM interview_sessions WHERE id=?",
            (sid,),
        )
        assert session[0] == "confirmed"

    def test_patient_sees_record_after_confirm(self, registered_patient):
        """After confirming, the record appears in patient's record list."""
        token, name, doctor_id = registered_patient

        # Quick interview + confirm
        start = _patient_api("POST", "/api/patient/interview/start", token=token)
        sid = start.json()["session_id"]

        for text in ["肚子疼两天了", "没有其他疾病", "没有过敏", "没有家族病史", "不抽烟不喝酒"]:
            _patient_api("POST", "/api/patient/interview/turn", token=token, json_body={
                "session_id": sid, "text": text,
            })

        _patient_api("POST", "/api/patient/interview/confirm", token=token, json_body={"session_id": sid})

        # Check patient records endpoint
        resp = _patient_api("GET", "/api/patient/records", token=token)
        assert resp.status_code == 200
        records = resp.json()
        interview_records = [r for r in records if r.get("record_type") == "interview_summary"]
        assert len(interview_records) >= 1, f"No interview_summary record found. Records: {records}"
