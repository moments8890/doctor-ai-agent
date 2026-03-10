"""数据访问层仓库测试：验证患者、病历及任务 Repository 的 CRUD 操作行为，使用真实内存数据库。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db.repositories import PatientRepository, RecordRepository
from db.repositories.tasks import TaskRepository
from db.models.medical_record import MedicalRecord


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
        content="胸痛 冠心病 随访",
        tags=["冠心病"],
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
    assert "胸痛" in by_patient[0].content

    by_doctor = await record_repo.list_for_doctor(
        doctor_id="repo_doc_2",
        limit=10,
    )
    assert len(by_doctor) == 1
    assert "冠心病" in by_doctor[0].content


async def test_task_repository_create_list_update_due_and_mark_notified(db_session):
    repo = TaskRepository(db_session)
    now = datetime.now(timezone.utc)
    due_at = now - timedelta(minutes=5)
    created = await repo.create(
        doctor_id="repo_doc_3",
        task_type="follow_up",
        title="随访提醒：王五",
        due_at=due_at,
    )
    assert created.id is not None
    assert created.status == "pending"

    listed = await repo.list_for_doctor(doctor_id="repo_doc_3")
    assert len(listed) == 1
    assert listed[0].id == created.id

    updated = await repo.update_status(task_id=created.id, doctor_id="repo_doc_3", status="completed")
    assert updated is not None
    assert updated.status == "completed"

    due = await repo.list_due_unnotified(now=now)
    assert all(t.id != created.id for t in due)

    await repo.update_status(task_id=created.id, doctor_id="repo_doc_3", status="pending")
    due = await repo.list_due_unnotified(now=now)
    assert any(t.id == created.id for t in due)

    # mark_notified is a no-op since notified_at column was removed; task remains due
    await repo.mark_notified(task_id=created.id, notified_at=now)
    due_after_notified = await repo.list_due_unnotified(now=now)
    assert any(t.id == created.id for t in due_after_notified)
