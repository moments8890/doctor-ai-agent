from __future__ import annotations

from db.repositories import PatientRepository, RecordRepository
from models.medical_record import MedicalRecord


async def test_patient_repository_create_find_and_list(db_session):
    repo = PatientRepository(db_session)
    created = await repo.create(
        doctor_id="repo_doc_1",
        name="张三",
        gender="男",
        age=40,
    )
    assert created.id is not None

    found = await repo.find_by_name("repo_doc_1", "张三")
    assert found is not None
    assert found.id == created.id

    listed = await repo.list_for_doctor("repo_doc_1")
    assert len(listed) == 1
    assert listed[0].name == "张三"


async def test_record_repository_create_and_query(db_session):
    patient_repo = PatientRepository(db_session)
    record_repo = RecordRepository(db_session)
    patient = await patient_repo.create(
        doctor_id="repo_doc_2",
        name="李四",
        gender=None,
        age=None,
    )
    record = MedicalRecord(
        chief_complaint="胸痛",
        diagnosis="冠心病",
        treatment_plan="随访",
    )
    created = await record_repo.create(
        doctor_id="repo_doc_2",
        record=record,
        patient_id=patient.id,
    )
    assert created.id is not None

    by_patient = await record_repo.list_for_patient(
        doctor_id="repo_doc_2",
        patient_id=patient.id,
        limit=10,
    )
    assert len(by_patient) == 1
    assert by_patient[0].chief_complaint == "胸痛"

    by_doctor = await record_repo.list_for_doctor(
        doctor_id="repo_doc_2",
        limit=10,
    )
    assert len(by_doctor) == 1
    assert by_doctor[0].diagnosis == "冠心病"
