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
from db.crud.patient import get_patient_for_doctor
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from domain.tasks.task_crud import run_due_task_cycle
from infra.observability.audit import audit
from utils.log import safe_create_task

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
    created_at: str
    patient_id: Optional[int]
    record_id: Optional[int]

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
            created_at=_iso(task.created_at) or "",
            patient_id=task.patient_id,
            record_id=task.record_id,
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
        tasks = await list_tasks(session, doctor_id, status=status, limit=limit, offset=offset)
    return [TaskOut.from_orm(t) for t in tasks]


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
        if body.patient_id is not None:
            patient = await get_patient_for_doctor(session, doctor_id, body.patient_id)
            if patient is None:
                raise HTTPException(status_code=404, detail="Patient not found")
        task = await create_task(
            session,
            doctor_id=doctor_id,
            task_type=body.task_type,
            title=body.title.strip(),
            content=body.content,
            patient_id=body.patient_id,
            due_at=due_at,
        )
    safe_create_task(audit(doctor_id, "create_task", "doctor_task", str(task.id)))
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
    safe_create_task(audit(doctor_id, "postpone_task", "doctor_task", str(task_id)))
    return TaskOut.from_orm(task)


@router.get("/record/{record_id}")
async def get_task_record(
    record_id: int,
    doctor_id: str,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Fetch a medical record by ID (for task detail view)."""
    from db.models import MedicalRecordDB, Patient
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    async with AsyncSessionLocal() as session:
        stmt = (
            select(MedicalRecordDB)
            .options(joinedload(MedicalRecordDB.patient))
            .where(
                MedicalRecordDB.id == record_id,
                MedicalRecordDB.doctor_id == resolved_doctor_id,
            )
        )
        record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    import json
    tags = []
    if record.tags:
        try:
            tags = json.loads(record.tags)
        except Exception:
            pass

    return {
        "id": record.id,
        "patient_name": record.patient.name if record.patient else None,
        "record_type": record.record_type or "visit",
        "content": record.content,
        "tags": tags,
        "needs_review": bool(record.needs_review) if record.needs_review is not None else False,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.post("/dev/run-notifier")
async def dev_run_notifier(
    doctor_id: str,
    include_manual: bool = True,
    force: bool = True,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Dev-only endpoint: trigger one background notification cycle immediately."""
    if not _env_flag_true("TASK_DEV_ENDPOINT_ENABLED", default=False):
        raise HTTPException(status_code=404, detail="Not found")
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="tasks.dev_notifier")
    return await run_due_task_cycle(
        doctor_id=resolved_doctor_id,
        include_manual=include_manual,
        force=force,
    )
