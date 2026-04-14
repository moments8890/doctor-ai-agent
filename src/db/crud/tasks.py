"""
医生任务的增删查改及状态更新的数据库操作。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import DoctorTask
from db.models.tasks import TaskStatus
from db.repositories import TaskRepository
from db.crud._common import _utcnow
from db.crud.doctor import _ensure_doctor_exists


async def create_task(
    session: AsyncSession,
    doctor_id: str,
    task_type: str,
    title: str,
    content: Optional[str] = None,
    patient_id: Optional[int] = None,
    record_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
    target: str = "doctor",
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
        target=target,
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
    """Atomically claim a task for notification by setting notified_at.

    Returns True if the claim succeeded (notified_at was NULL), False if
    another process already claimed it.  The caller should only send the
    notification when this returns True.
    """
    from sqlalchemy import update as _update
    now = _utcnow()
    result = await session.execute(
        _update(DoctorTask)
        .where(
            DoctorTask.id == task_id,
            DoctorTask.status == TaskStatus.pending,
            DoctorTask.notified_at.is_(None),
            DoctorTask.due_at <= now,
        )
        .values(notified_at=now, updated_at=now)
    )
    await session.commit()
    return (result.rowcount or 0) > 0


async def revert_task_to_pending(
    session: AsyncSession,
    task_id: int,
) -> None:
    """Clear notified_at on send failure so the next cycle can retry."""
    from sqlalchemy import update as _update
    await session.execute(
        _update(DoctorTask)
        .where(DoctorTask.id == task_id)
        .values(notified_at=None, updated_at=_utcnow())
    )
    await session.commit()


async def update_task_notes(
    session: AsyncSession,
    task_id: int,
    doctor_id: str,
    notes: str,
) -> Optional[DoctorTask]:
    return await TaskRepository(session).update_notes(
        task_id=task_id, doctor_id=doctor_id, notes=notes
    )
