from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DoctorTask


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
            status="pending",
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
    ) -> List[DoctorTask]:
        stmt = select(DoctorTask).where(DoctorTask.doctor_id == doctor_id)
        if status is not None:
            stmt = stmt.where(DoctorTask.status == status)
        result = await self.session.execute(stmt.order_by(DoctorTask.created_at.desc()))
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
                DoctorTask.status == "pending",
                DoctorTask.due_at <= now,
                DoctorTask.notified_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def mark_notified(self, *, task_id: int, notified_at: datetime) -> None:
        result = await self.session.execute(select(DoctorTask).where(DoctorTask.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return
        task.notified_at = notified_at
        await self.session.commit()
