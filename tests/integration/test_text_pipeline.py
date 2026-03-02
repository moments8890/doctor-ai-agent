"""Integration tests for the text → structured record → DB pipeline.

Covers four key scenarios:
  1. Patient name in input          → one-shot save
  2. No patient name                → agent asks, name provided, then saves
  3. Emergency input                → record saved, chief_complaint populated
  4. Sparse input (no treatment)    → treatment_plan must be null (no hallucination)

Requires: running server + Ollama (auto-skipped otherwise).
"""
import pytest

from tests.integration.conftest import chat, db_record


@pytest.mark.integration
def test_name_in_text_saves_record():
    """Patient name present in input → record created and persisted in DB."""
    doctor_id = "inttest_text_1"

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

    # Turn 1: clinical text without a name
    data = chat("突发胸痛两小时，伴大汗", doctor_id=doctor_id)
    assert "叫什么名字" in data["reply"], "Agent should ask for patient name"
    assert data["record"] is None

    # Turn 2: doctor provides the name
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

    data = chat("赵丽，女，60岁，高血压控制差，服药依从性一般", doctor_id=doctor_id)

    assert data["record"] is not None
    treatment = data["record"].get("treatment_plan")
    assert treatment is None, (
        f"LLM fabricated a treatment plan not in input: '{treatment}'"
    )
