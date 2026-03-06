"""Integration tests for the doctor-input text pipeline (`/api/records/chat`).

These tests are true end-to-end from doctor text input through:
  doctor text -> intent dispatch -> structuring -> DB write -> API reply.

Core coverage:
  1. One-shot patient+record save when name is present
  2. Two-turn clarification flow when name is missing
  3. Emergency-like text still yields persisted structured record
  4. Sparse note does not hallucinate treatment content
  5. Repeated records for same patient do not duplicate patient rows
  6. Query-by-name and list-patients conversational intents work

Assertions are intentionally DB-backed (via direct sqlite reads) to ensure
we validate persistence, not only API response payloads.

Requires: running server + Ollama (auto-skipped otherwise).
"""
import sqlite3
import uuid

import pytest

from e2e.integration.conftest import DB_PATH, chat, db_record


def _patient_count(doctor_id: str, patient_name: str) -> int:
    """Return patient row count for one doctor+name pair.

    Used to verify dedup behavior (same patient should not be re-created when
    new records for that name arrive).
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM patients WHERE doctor_id=? AND name=?",
            (doctor_id, patient_name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _record_count_for_patient(doctor_id: str, patient_name: str) -> int:
    """Return total record count joined through patients table.

    We use a join here so tests validate both patient linkage and record writes
    for the doctor/name pair.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT COUNT(1)
            FROM medical_records r
            JOIN patients p ON p.id = r.patient_id
            WHERE p.doctor_id=? AND p.name=?
            """,
            (doctor_id, patient_name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


@pytest.mark.integration
def test_name_in_text_saves_record():
    """Patient name present in input → record created and persisted in DB."""
    doctor_id = "inttest_text_1"

    # Single-turn input with demographics + complaint should route directly
    # to add_record and persist both patient linkage and record data.
    data = chat("张伟，男，52岁，劳力性胸闷三周，休息后缓解", doctor_id=doctor_id)

    assert data["record"] is not None, "API should return a record"
    assert data["record"]["chief_complaint"], "chief_complaint must not be null"

    rec = db_record(doctor_id, "张伟")
    assert rec is not None, "Patient '张伟' not found in DB"
    assert rec[0], "chief_complaint is null in DB"


@pytest.mark.integration
def test_missing_name_asks_then_saves():
    """No name in text → agent asks for name → doctor provides it → record saved."""
    doctor_id = "inttest_text_2"

    # Turn 1: no name -> assistant should ask for patient name.
    data = chat("突发胸痛两小时，伴大汗", doctor_id=doctor_id)
    assert "叫什么名字" in data["reply"], "Agent should ask for patient name"
    assert data["record"] is None

    # Turn 2: name-only follow-up with previous history should deterministically
    # complete add_record flow and persist to DB.
    history = [
        {"role": "user", "content": "突发胸痛两小时，伴大汗"},
        {"role": "assistant", "content": data["reply"]},
    ]
    data2 = chat("陈明", history=history, doctor_id=doctor_id)

    assert data2["record"] is not None, "Record should be returned after name provided"
    rec = db_record(doctor_id, "陈明")
    assert rec is not None, "Patient '陈明' not found in DB after name provided"


@pytest.mark.integration
def test_emergency_input_produces_record():
    """STEMI / emergency input → record saved with chief_complaint populated."""
    doctor_id = "inttest_text_3"

    # Emergency lexical cues should still produce a valid structured record
    # and be persisted with non-null chief complaint.
    data = chat(
        "韩伟，男，59岁，突发胸痛两小时，ST段抬高，急诊PCI绿色通道",
        doctor_id=doctor_id,
    )

    assert data["record"] is not None
    assert data["record"]["chief_complaint"]
    rec = db_record(doctor_id, "韩伟")
    assert rec is not None, "Emergency record not saved to DB"


@pytest.mark.integration
def test_sparse_input_no_hallucinated_treatment():
    """Sparse input with no treatment mentioned → treatment_plan must be null."""
    doctor_id = "inttest_text_4"

    # Note intentionally omits explicit treatment directives.
    # Structuring output should keep treatment_plan null.
    data = chat("赵丽，女，60岁，高血压控制差，服药依从性一般", doctor_id=doctor_id)

    assert data["record"] is not None
    treatment = data["record"].get("treatment_plan")
    assert treatment is None, (
        f"LLM fabricated a treatment plan not in input: '{treatment}'"
    )


@pytest.mark.integration
def test_existing_patient_second_record_does_not_duplicate_patient():
    """Two add-record messages for same name should keep one patient row."""
    doctor_id = f"inttest_text_dup_{uuid.uuid4().hex[:8]}"
    patient_name = "周强"

    # First note creates patient + first record.
    first = chat(f"{patient_name}，男，48岁，胸闷1周，活动后加重", doctor_id=doctor_id)
    assert first["record"] is not None

    # Second note for same name should append record, not duplicate patient row.
    second = chat(f"{patient_name}，昨晚胸痛加重，伴出汗", doctor_id=doctor_id)
    assert second["record"] is not None

    assert _patient_count(doctor_id, patient_name) == 1
    assert _record_count_for_patient(doctor_id, patient_name) >= 2


@pytest.mark.integration
def test_query_records_by_name_returns_patient_history():
    """Doctor asks to query a named patient after one saved encounter."""
    doctor_id = f"inttest_text_query_{uuid.uuid4().hex[:8]}"
    patient_name = "钱芳"

    _ = chat(f"{patient_name}，女，63岁，反复胸闷3天", doctor_id=doctor_id)
    result = chat(f"查询{patient_name}的病历", doctor_id=doctor_id)

    assert f"患者【{patient_name}】最近" in result["reply"]
    assert "主诉" in result["reply"]


@pytest.mark.integration
def test_list_patients_returns_created_names():
    """Doctor asks for patient list after creating multiple patients."""
    doctor_id = f"inttest_text_list_{uuid.uuid4().hex[:8]}"
    p1 = "孙明"
    p2 = "吴静"

    _ = chat(f"{p1}，男，55岁，心悸2天", doctor_id=doctor_id)
    _ = chat(f"{p2}，女，47岁，胸痛半天", doctor_id=doctor_id)

    result = chat("所有患者", doctor_id=doctor_id)
    assert p1 in result["reply"]
    assert p2 in result["reply"]
    assert "共" in result["reply"] and "位患者" in result["reply"]
