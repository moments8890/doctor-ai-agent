"""医生输入文本管道集成测试（/api/records/chat）。

Integration tests for the doctor-input text pipeline. Two-step flow:
  doctor text → pending draft → confirm → DB write.

Assertions are provider-agnostic: validate DB state, not LLM phrasing.
Requires: running server + LLM provider (auto-skipped otherwise).
"""

import sqlite3
import uuid

import pytest

from tests.integration.conftest import DB_PATH, chat, db_record, chat_and_confirm


def _patient_count(doctor_id, patient_name):
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM patients WHERE doctor_id=? AND name=?",
            (doctor_id, patient_name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _record_count_for_patient(doctor_id, patient_name):
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
    """Patient name present → draft → confirm → persisted in DB."""
    doctor_id = f"inttest_text_1_{uuid.uuid4().hex[:8]}"
    chat_and_confirm("张伟，男，52岁，劳力性胸闷三周，休息后缓解", doctor_id=doctor_id)
    rec = db_record(doctor_id, "张伟")
    assert rec is not None, "Patient '张伟' not found in DB"
    assert rec[0], "content is null in DB"


@pytest.mark.integration
def test_missing_name_asks_then_saves():
    """No name → agent asks → doctor provides → confirm → record saved."""
    doctor_id = f"inttest_text_2_{uuid.uuid4().hex[:8]}"
    data = chat("突发胸痛两小时，伴大汗", doctor_id=doctor_id)
    assert data["record"] is None, "Record should not be created without patient name"
    history = [
        {"role": "user", "content": "突发胸痛两小时，伴大汗"},
        {"role": "assistant", "content": data["reply"]},
    ]
    chat_and_confirm("陈明", history=history, doctor_id=doctor_id)
    rec = db_record(doctor_id, "陈明")
    assert rec is not None, "Patient '陈明' not found in DB after name + confirm"


@pytest.mark.integration
def test_emergency_input_produces_record():
    """STEMI / emergency input → record saved with content."""
    doctor_id = f"inttest_text_3_{uuid.uuid4().hex[:8]}"
    chat_and_confirm(
        "韩伟，男，59岁，突发胸痛两小时，ST段抬高，急诊PCI绿色通道",
        doctor_id=doctor_id,
    )
    rec = db_record(doctor_id, "韩伟")
    assert rec is not None, "Emergency record not saved to DB"
    assert rec[0], "content is null for emergency record"


@pytest.mark.integration
def test_sparse_input_no_hallucinated_treatment():
    """Sparse input → content must not contain fabricated treatment."""
    doctor_id = f"inttest_text_4_{uuid.uuid4().hex[:8]}"
    chat_and_confirm(
        "赵丽，女，60岁，头晕2天，高血压控制差，血压160/100mmHg，服药依从性一般",
        doctor_id=doctor_id,
    )
    rec = db_record(doctor_id, "赵丽")
    assert rec is not None, "Record not saved to DB for sparse note"
    db_content = rec[0] or ""
    _AGGRESSIVE = ["手术", "介入", "支架", "搭桥"]
    hallucinated = [kw for kw in _AGGRESSIVE if kw in db_content]
    assert not hallucinated, f"Hallucinated treatment in DB content: {hallucinated}"


@pytest.mark.integration
def test_existing_patient_second_record_does_not_duplicate_patient():
    """Two records for same name → one patient row, two records."""
    doctor_id = f"inttest_text_dup_{uuid.uuid4().hex[:8]}"
    name = "周强"
    chat_and_confirm(f"{name}，男，48岁，胸闷1周，活动后加重", doctor_id=doctor_id)
    chat_and_confirm(f"{name}，昨晚胸痛加重，伴出汗", doctor_id=doctor_id)
    assert _patient_count(doctor_id, name) == 1
    assert _record_count_for_patient(doctor_id, name) >= 2


@pytest.mark.integration
def test_query_records_by_name_returns_patient_history():
    """Query a named patient after one saved encounter."""
    doctor_id = f"inttest_text_query_{uuid.uuid4().hex[:8]}"
    name = "钱芳"
    chat_and_confirm(f"{name}，女，63岁，反复胸闷3天", doctor_id=doctor_id)
    rec = db_record(doctor_id, name)
    assert rec is not None, f"Record for '{name}' not in DB"
    result = chat(f"查询{name}的病历", doctor_id=doctor_id)
    assert name in result["reply"], f"Reply should mention '{name}'"


@pytest.mark.integration
def test_list_patients_returns_created_names():
    """Patient list after creating multiple patients."""
    doctor_id = f"inttest_text_list_{uuid.uuid4().hex[:8]}"
    p1, p2 = "孙明", "吴静"
    chat_and_confirm(f"{p1}，男，55岁，反复心悸2天，心电图示房颤", doctor_id=doctor_id)
    chat_and_confirm(f"{p2}，女，47岁，活动后胸痛半天，伴气短", doctor_id=doctor_id)
    assert _patient_count(doctor_id, p1) == 1, f"{p1} not found in DB"
    assert _patient_count(doctor_id, p2) == 1, f"{p2} not found in DB"
    result = chat("所有患者", doctor_id=doctor_id)
    assert p1 in result["reply"], f"Reply should mention '{p1}'"
    assert p2 in result["reply"], f"Reply should mention '{p2}'"
