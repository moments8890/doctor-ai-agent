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
    scheduled_for: Optional[datetime] = None,
    remind_at: Optional[datetime] = None,
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
        scheduled_for=scheduled_for,
        remind_at=remind_at,
    )


async def list_tasks(
    session: AsyncSession,
    doctor_id: str,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> List[DoctorTask]:
    return await TaskRepository(session).list_for_doctor(
        doctor_id=doctor_id, status=status, limit=limit, offset=offset,
    )


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


async def get_task_by_id(
    session: AsyncSession,
    task_id: int,
    doctor_id: str,
) -> Optional[DoctorTask]:
    return await TaskRepository(session).get_by_id(task_id=task_id, doctor_id=doctor_id)


async def update_task_due_at(
    session: AsyncSession,
    task_id: int,
    doctor_id: str,
    due_at: datetime,
) -> Optional[DoctorTask]:
    return await TaskRepository(session).update_due_at(
        task_id=task_id, doctor_id=doctor_id, due_at=due_at
    )


async def mark_task_notified(
    session: AsyncSession,
    task_id: int,
) -> bool:
    """Atomically mark a task as notified (pending → notified).

    Returns True if the transition succeeded, False if another process
    already claimed it.  The caller should only send the notification
    when this returns True.
    """
    from sqlalchemy import select as _select, update as _update
    result = await session.execute(
        _update(DoctorTask)
        .where(DoctorTask.id == task_id, DoctorTask.status == "pending")
        .values(status="notified", updated_at=_utcnow())
    )
    await session.commit()
    return (result.rowcount or 0) > 0


async def revert_task_to_pending(
    session: AsyncSession,
    task_id: int,
) -> None:
    """Revert a 'notified' task back to 'pending' (used when send fails after mark)."""
    from sqlalchemy import update as _update
    await session.execute(
        _update(DoctorTask)
        .where(DoctorTask.id == task_id, DoctorTask.status == "notified")
        .values(status="pending", updated_at=_utcnow())
    )
    await session.commit()
