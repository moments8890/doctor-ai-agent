"""
任务仓储层：提供医生任务的过滤查询和状态更新接口。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DoctorTask
from db.models.tasks import TaskStatus


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        doctor_id: str,
        task_type: str,
        title: str,
        content: Optional[str] = None,
        patient_id: Optional[int] = None,
        record_id: Optional[int] = None,
        due_at: Optional[datetime] = None,
    ) -> DoctorTask:
        task = DoctorTask(
            doctor_id=doctor_id,
            task_type=task_type,
            title=title,
            content=content,
            patient_id=patient_id,
            record_id=record_id,
            due_at=due_at,
            status=TaskStatus.pending,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def list_for_doctor(
        self,
        *,
        doctor_id: str,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[DoctorTask]:
        stmt = select(DoctorTask).where(DoctorTask.doctor_id == doctor_id)
        if status is not None:
            stmt = stmt.where(DoctorTask.status == status)
        stmt = stmt.order_by(DoctorTask.created_at.desc())
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        *,
        task_id: int,
        doctor_id: str,
        status: str,
    ) -> Optional[DoctorTask]:
        result = await self.session.execute(
            select(DoctorTask).where(DoctorTask.id == task_id, DoctorTask.doctor_id == doctor_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            return None
        task.status = status
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def list_due_unnotified(self, *, now: datetime) -> List[DoctorTask]:
        result = await self.session.execute(
            select(DoctorTask).where(
                DoctorTask.status == TaskStatus.pending,
                DoctorTask.due_at <= now,
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, *, task_id: int, doctor_id: str) -> Optional[DoctorTask]:
        result = await self.session.execute(
            select(DoctorTask).where(DoctorTask.id == task_id, DoctorTask.doctor_id == doctor_id)
        )
        return result.scalar_one_or_none()

    async def update_due_at(
        self,
        *,
        task_id: int,
        doctor_id: str,
        due_at: datetime,
    ) -> Optional[DoctorTask]:
        result = await self.session.execute(
            select(DoctorTask).where(DoctorTask.id == task_id, DoctorTask.doctor_id == doctor_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            return None
        task.due_at = due_at
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def mark_notified(self, *, task_id: int, notified_at: datetime) -> None:
        """Transition task from 'pending' to 'notified'."""
        from sqlalchemy import update as _update
        await self.session.execute(
            _update(DoctorTask)
            .where(DoctorTask.id == task_id, DoctorTask.status == TaskStatus.pending)
            .values(status=TaskStatus.notified, updated_at=notified_at)
        )
        await self.session.commit()
