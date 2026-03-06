from __future__ import annotations

from datetime import datetime

from db.models import DoctorTask, MedicalRecordDB, NeuroCaseDB, Patient, SystemPrompt


def test_model_str_methods():
    prompt = SystemPrompt(key="structuring", content="x")
    assert str(prompt) == "structuring"

    patient = Patient(doctor_id="doc", name="张三", gender=None, year_of_birth=None)
    assert str(patient) == "张三"

    record_with_date = MedicalRecordDB(
        doctor_id="doc",
        chief_complaint="胸痛",
        created_at=datetime(2026, 3, 2, 10, 0, 0),
    )
    assert str(record_with_date) == "胸痛 [2026-03-02]"

    record_no_date = MedicalRecordDB(doctor_id="doc", chief_complaint=None, created_at=None)
    assert str(record_no_date) == "— [—]"

    neuro_with_date = NeuroCaseDB(
        doctor_id="doc",
        chief_complaint="偏瘫",
        created_at=datetime(2026, 3, 2, 10, 0, 0),
    )
    assert str(neuro_with_date) == "偏瘫 [2026-03-02]"

    neuro_no_date = NeuroCaseDB(doctor_id="doc", chief_complaint=None, created_at=None)
    assert str(neuro_no_date) == "— [—]"

    task = DoctorTask(doctor_id="doc", task_type="follow_up", title="随访提醒：张三")
    assert str(task) == "[follow_up] 随访提醒：张三"
