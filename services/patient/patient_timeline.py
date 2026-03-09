"""
患者时间线构建：将病历和任务按时间排序，生成患者就诊历史摘要。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DoctorTask, MedicalRecordDB, Patient


def _event_from_record(record: MedicalRecordDB) -> Dict[str, object]:
    return {
        "type": "record",
        "timestamp": record.created_at.isoformat() if record.created_at else None,
        "id": record.id,
        "payload": {
            "content": record.content,
            "tags": record.tags,
            "record_type": record.record_type,
        },
    }


def _event_from_task(task: DoctorTask) -> Dict[str, object]:
    return {
        "type": "task",
        "timestamp": task.created_at.isoformat() if task.created_at else None,
        "id": task.id,
        "payload": {
            "task_type": task.task_type,
            "title": task.title,
            "status": task.status,
            "due_at": task.due_at.isoformat() if task.due_at else None,
        },
    }


async def build_patient_timeline(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
    limit: int = 100,
) -> Optional[Dict[str, object]]:
    patient_result = await session.execute(
        select(Patient).where(Patient.id == patient_id, Patient.doctor_id == doctor_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        return None

    records_result = await session.execute(
        select(MedicalRecordDB)
        .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id == patient_id)
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(limit)
    )
    tasks_result = await session.execute(
        select(DoctorTask)
        .where(DoctorTask.doctor_id == doctor_id, DoctorTask.patient_id == patient_id)
        .order_by(DoctorTask.created_at.desc())
        .limit(limit)
    )

    events: List[Dict[str, object]] = []
    events.extend(_event_from_record(row) for row in records_result.scalars().all())
    events.extend(_event_from_task(row) for row in tasks_result.scalars().all())
    events.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    return {
        "patient": {
            "id": patient.id,
            "name": patient.name,
        },
        "events": events,
    }
