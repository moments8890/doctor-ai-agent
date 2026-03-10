from __future__ import annotations

from datetime import datetime

from db.models import DoctorTask, MedicalRecordDB, Patient, SystemPrompt


def test_model_str_methods():
    prompt = SystemPrompt(key="structuring", content="x")
    assert str(prompt) == "structuring"

    patient = Patient(doctor_id="doc", name="张三", gender=None, year_of_birth=None)
    assert str(patient) == "张三"

    record_with_date = MedicalRecordDB(
        doctor_id="doc",
        content="胸痛",
        created_at=datetime(2026, 3, 2, 10, 0, 0),
    )
    assert "胸痛" in str(record_with_date)
    assert "2026-03-02" in str(record_with_date)

    record_no_date = MedicalRecordDB(doctor_id="doc", content=None, created_at=None)
    assert "—" in str(record_no_date)

    task = DoctorTask(doctor_id="doc", task_type="follow_up", title="随访提醒：张三")
    assert str(task) == "[follow_up] 随访提醒：张三"
