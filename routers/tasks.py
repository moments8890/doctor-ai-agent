from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud import list_tasks, update_task_status

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskOut(BaseModel):
    id: int
    doctor_id: str
    task_type: str
    title: str
    content: Optional[str]
    status: str
    due_at: Optional[str]
    notified_at: Optional[str]
    created_at: str
    patient_id: Optional[int]
    record_id: Optional[int]
    trigger_source: Optional[str]
    trigger_reason: Optional[str]

    @classmethod
    def from_orm(cls, task: object) -> "TaskOut":
        def _iso(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return cls(
            id=task.id,
            doctor_id=task.doctor_id,
            task_type=task.task_type,
            title=task.title,
            content=task.content,
            status=task.status,
            due_at=_iso(task.due_at),
            notified_at=_iso(task.notified_at),
            created_at=_iso(task.created_at) or "",
            patient_id=task.patient_id,
            record_id=task.record_id,
            trigger_source=task.trigger_source,
            trigger_reason=task.trigger_reason,
        )


class TaskStatusUpdate(BaseModel):
    status: str


@router.get("", response_model=List[TaskOut])
async def get_tasks(doctor_id: str, status: Optional[str] = None) -> List[TaskOut]:
    async with AsyncSessionLocal() as session:
        tasks = await list_tasks(session, doctor_id, status=status)
    return [TaskOut.from_orm(t) for t in tasks]


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(task_id: int, doctor_id: str, body: TaskStatusUpdate) -> TaskOut:
    allowed = {"completed", "cancelled"}
    if body.status not in allowed:
        raise HTTPException(status_code=422, detail=f"status must be one of {allowed}")
    async with AsyncSessionLocal() as session:
        task = await update_task_status(session, task_id, doctor_id, body.status)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut.from_orm(task)
