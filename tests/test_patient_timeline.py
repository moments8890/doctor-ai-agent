"""患者时间线测试：验证患者就诊事件与任务的时间轴聚合查询及缺失患者的处理逻辑。"""

from __future__ import annotations

from datetime import datetime

from db.crud import create_patient, save_record
from db.models import DoctorTask
from db.models.medical_record import MedicalRecord
from services.patient.patient_timeline import build_patient_timeline


async def test_build_patient_timeline_includes_record_and_task(db_session):
    patient = await create_patient(db_session, "doc1", "张三", "男", 45)
    record = MedicalRecord(
        content="胸闷 2天 高血压 观察 两周后复诊",
        tags=["高血压", "两周后复诊"],
    )
    await save_record(db_session, "doc1", record, patient.id)

    db_session.add(
        DoctorTask(
            doctor_id="doc1",
            patient_id=patient.id,
            task_type="follow_up",
            title="随访提醒：张三",
            status="pending",
            created_at=datetime(2026, 3, 2, 10, 0, 0),
        )
    )
    await db_session.commit()

    data = await build_patient_timeline(db_session, doctor_id="doc1", patient_id=patient.id, limit=100)

    assert data is not None
    assert data["patient"]["name"] == "张三"
    types = {item["type"] for item in data["events"]}
    assert "record" in types
    assert "task" in types


async def test_build_patient_timeline_returns_none_for_missing_patient(db_session):
    data = await build_patient_timeline(db_session, doctor_id="doc1", patient_id=999, limit=100)
    assert data is None
