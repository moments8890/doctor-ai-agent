"""
任务管理路由：提供随访任务的创建、查询和状态更新 API 端点。
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud import list_tasks, update_task_status, create_task, get_task_by_id, update_task_due_at
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from services.notify.tasks import run_due_task_cycle
from services.observability.audit import audit

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_VALID_TASK_TYPES = {"follow_up", "medication", "lab_review", "referral", "imaging", "appointment", "general"}


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


class TaskDueUpdate(BaseModel):
    due_at: str  # ISO 8601 datetime string


class TaskCreate(BaseModel):
    task_type: str
    title: str
    due_at: Optional[str] = None
    patient_id: Optional[int] = None
    content: Optional[str] = None


def _env_flag_true(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_due_at(due_at_str: str) -> datetime:
    """Parse ISO datetime string; treat bare dates (YYYY-MM-DD) as end-of-day UTC."""
    try:
        dt = datetime.fromisoformat(due_at_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid due_at format: {due_at_str!r}")


@router.get("", response_model=List[TaskOut])
async def get_tasks(
    doctor_id: str,
    status: Optional[str] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    authorization: Optional[str] = Header(default=None),
) -> List[TaskOut]:
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="tasks.get")
    return await _get_tasks_for_doctor(resolved_doctor_id, status=status, limit=limit, offset=offset)


async def _get_tasks_for_doctor(
    doctor_id: str,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[TaskOut]:
    async with AsyncSessionLocal() as session:
        tasks = await list_tasks(session, doctor_id, status=status)
    all_tasks = [TaskOut.from_orm(t) for t in tasks]
    return all_tasks[offset:offset + limit]


@router.post("", response_model=TaskOut, status_code=201)
async def create_task_endpoint(
    doctor_id: str,
    body: TaskCreate,
    authorization: Optional[str] = Header(default=None),
) -> TaskOut:
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="tasks.create")
    return await _create_task_for_doctor(resolved_doctor_id, body)


async def _create_task_for_doctor(doctor_id: str, body: TaskCreate) -> TaskOut:
    if body.task_type not in _VALID_TASK_TYPES:
        raise HTTPException(status_code=422, detail=f"task_type must be one of {_VALID_TASK_TYPES}")
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="title must not be empty")
    due_at = _parse_due_at(body.due_at) if body.due_at else None
    async with AsyncSessionLocal() as session:
        task = await create_task(
            session,
            doctor_id=doctor_id,
            task_type=body.task_type,
            title=body.title.strip(),
            content=body.content,
            patient_id=body.patient_id,
            due_at=due_at,
        )
    asyncio.create_task(audit(doctor_id, "create_task", "doctor_task", str(task.id)))
    return TaskOut.from_orm(task)


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
    enforce_doctor_rate_limit(resolved_doctor_id, scope="tasks.patch")
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


@router.patch("/{task_id}/due", response_model=TaskOut)
async def patch_task_due(
    task_id: int,
    doctor_id: str,
    body: TaskDueUpdate,
    authorization: Optional[str] = Header(default=None),
) -> TaskOut:
    """Postpone (reschedule) a task by updating its due_at."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="tasks.patch")
    return await _postpone_task_for_doctor(task_id, resolved_doctor_id, body)


async def _postpone_task_for_doctor(task_id: int, doctor_id: str, body: TaskDueUpdate) -> TaskOut:
    due_at = _parse_due_at(body.due_at)
    async with AsyncSessionLocal() as session:
        task = await update_task_due_at(session, task_id, doctor_id, due_at)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    asyncio.create_task(audit(doctor_id, "postpone_task", "doctor_task", str(task_id)))
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
    if doctor_id:
        enforce_doctor_rate_limit(doctor_id, scope="tasks.dev_notifier")
    return await run_due_task_cycle(
        doctor_id=doctor_id,
        include_manual=include_manual,
        force=force,
    )
