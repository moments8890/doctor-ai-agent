"""
医生任务的增删查改及状态更新的数据库操作。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import DoctorTask
from db.repositories import TaskRepository
from db.crud.doctor import _ensure_doctor_exists


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_task(
    session: AsyncSession,
    doctor_id: str,
    task_type: str,
    title: str,
    content: Optional[str] = None,
    patient_id: Optional[int] = None,
    record_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
) -> DoctorTask:
    doctor_id = await _ensure_doctor_exists(session, doctor_id)
    return await TaskRepository(session).create(
        doctor_id=doctor_id,
        task_type=task_type,
        title=title,
        content=content,
        patient_id=patient_id,
        record_id=record_id,
        due_at=due_at,
    )


async def list_tasks(
    session: AsyncSession,
    doctor_id: str,
    status: Optional[str] = None,
) -> List[DoctorTask]:
    return await TaskRepository(session).list_for_doctor(doctor_id=doctor_id, status=status)


async def update_task_status(
    session: AsyncSession,
    task_id: int,
    doctor_id: str,
    status: str,
) -> Optional[DoctorTask]:
    return await TaskRepository(session).update_status(
        task_id=task_id,
        doctor_id=doctor_id,
        status=status,
    )


async def get_due_tasks(
    session: AsyncSession,
    now: datetime,
) -> List[DoctorTask]:
    return await TaskRepository(session).list_due_unnotified(now=now)


async def mark_task_notified(
    session: AsyncSession,
    task_id: int,
) -> None:
    await TaskRepository(session).mark_notified(task_id=task_id, notified_at=_utcnow())
