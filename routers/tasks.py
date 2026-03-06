from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud import list_tasks, update_task_status
from services.request_auth import resolve_doctor_id_from_auth_or_fallback
from services.tasks import run_due_task_cycle

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


def _env_flag_true(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@router.get("", response_model=List[TaskOut])
async def get_tasks(
    doctor_id: str,
    status: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
) -> List[TaskOut]:
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    return await _get_tasks_for_doctor(resolved_doctor_id, status=status)


async def _get_tasks_for_doctor(doctor_id: str, status: Optional[str] = None) -> List[TaskOut]:
    async with AsyncSessionLocal() as session:
        tasks = await list_tasks(session, doctor_id, status=status)
    return [TaskOut.from_orm(t) for t in tasks]


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(
    task_id: int,
    doctor_id: str,
    body: TaskStatusUpdate,
    authorization: Optional[str] = Header(default=None),
) -> TaskOut:
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    return await _patch_task_for_doctor(task_id, resolved_doctor_id, body)


async def _patch_task_for_doctor(task_id: int, doctor_id: str, body: TaskStatusUpdate) -> TaskOut:
    allowed = {"completed", "cancelled"}
    if body.status not in allowed:
        raise HTTPException(status_code=422, detail=f"status must be one of {allowed}")
    async with AsyncSessionLocal() as session:
        task = await update_task_status(session, task_id, doctor_id, body.status)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut.from_orm(task)


@router.post("/dev/run-notifier")
async def dev_run_notifier(
    doctor_id: Optional[str] = None,
    include_manual: bool = True,
    force: bool = True,
) -> dict:
    """Dev-only endpoint: trigger one background notification cycle immediately."""
    if not _env_flag_true("TASK_DEV_ENDPOINT_ENABLED", default=False):
        raise HTTPException(status_code=404, detail="Not found")
    return await run_due_task_cycle(
        doctor_id=doctor_id,
        include_manual=include_manual,
        force=force,
    )
