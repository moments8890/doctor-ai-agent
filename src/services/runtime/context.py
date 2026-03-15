"""Load / save DoctorCtx and chat_archive operations (ADR 0011 §2, §3)."""
from __future__ import annotations

import json
from typing import List, Optional

from db.engine import AsyncSessionLocal
from db.models.doctor import ChatArchive, DoctorContext
from services.runtime.models import DoctorCtx, MemoryState, WorkflowState
from sqlalchemy import select
from utils.log import log


async def load_context(doctor_id: str) -> DoctorCtx:
    """Load doctor context from DB. Returns empty context if none exists."""
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(DoctorContext)
                .where(DoctorContext.doctor_id == doctor_id)
                .limit(1)
            )
        ).scalar_one_or_none()

    if row is None:
        return DoctorCtx(doctor_id=doctor_id)

    workflow = WorkflowState()
    if row.workflow_json:
        try:
            w = json.loads(row.workflow_json)
            workflow.patient_id = w.get("patient_id")
            workflow.patient_name = w.get("patient_name")
            workflow.pending_draft_id = w.get("pending_draft_id")
        except (json.JSONDecodeError, TypeError) as e:
            log(f"[context] bad workflow_json doctor={doctor_id}: {e}")

    memory = MemoryState()
    if row.memory_json:
        try:
            m = json.loads(row.memory_json)
            memory.candidate_patient = m.get("candidate_patient")
            memory.working_note = m.get("working_note")
            memory.summary = m.get("summary")
        except (json.JSONDecodeError, TypeError) as e:
            log(f"[context] bad memory_json doctor={doctor_id}: {e}")

    return DoctorCtx(doctor_id=doctor_id, workflow=workflow, memory=memory)


def _serialize_workflow(ctx: DoctorCtx) -> str:
    return json.dumps({
        "patient_id": ctx.workflow.patient_id,
        "patient_name": ctx.workflow.patient_name,
        "pending_draft_id": ctx.workflow.pending_draft_id,
    }, ensure_ascii=False)


def _serialize_memory(ctx: DoctorCtx) -> str:
    return json.dumps({
        "candidate_patient": ctx.memory.candidate_patient,
        "working_note": ctx.memory.working_note,
        "summary": ctx.memory.summary,
    }, ensure_ascii=False)


async def save_context(ctx: DoctorCtx) -> None:
    """Atomic upsert — INSERT ON CONFLICT UPDATE. No SELECT-then-INSERT race."""
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    workflow_json = _serialize_workflow(ctx)
    memory_json = _serialize_memory(ctx)

    async with AsyncSessionLocal() as db:
        dialect = db.bind.dialect.name if db.bind else "sqlite"

        if dialect == "sqlite":
            stmt = (
                sqlite_insert(DoctorContext)
                .values(
                    doctor_id=ctx.doctor_id,
                    workflow_json=workflow_json,
                    memory_json=memory_json,
                )
                .on_conflict_do_update(
                    index_elements=[DoctorContext.doctor_id],
                    set_={
                        "workflow_json": workflow_json,
                        "memory_json": memory_json,
                    },
                )
            )
        else:
            # PostgreSQL / MySQL
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = (
                pg_insert(DoctorContext)
                .values(
                    doctor_id=ctx.doctor_id,
                    workflow_json=workflow_json,
                    memory_json=memory_json,
                )
                .on_conflict_do_update(
                    index_elements=[DoctorContext.doctor_id],
                    set_={
                        "workflow_json": workflow_json,
                        "memory_json": memory_json,
                    },
                )
            )

        await db.execute(stmt)
        await db.commit()


async def get_recent_turns(doctor_id: str, limit: int = 20) -> List[dict]:
    """Read recent turns from chat_archive for conversation context."""
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(ChatArchive)
                .where(ChatArchive.doctor_id == doctor_id)
                .order_by(ChatArchive.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


async def archive_turns(
    doctor_id: str,
    user_text: str,
    assistant_reply: str,
    patient_id: Optional[int] = None,
) -> None:
    """Append user + assistant turns to chat_archive."""
    from db.crud import append_chat_archive
    turns = [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": assistant_reply},
    ]
    async with AsyncSessionLocal() as db:
        await append_chat_archive(db, doctor_id, turns, patient_id=patient_id)
        await db.commit()


async def has_pending_draft(doctor_id: str) -> bool:
    """Lightweight read-only check for a pending draft (public API)."""
    ctx = await load_context(doctor_id)
    return bool(ctx.workflow.pending_draft_id)


async def clear_pending_draft_id(doctor_id: str) -> None:
    """Clear pending_draft_id in context (called by REST confirm/abandon)."""
    ctx = await load_context(doctor_id)
    ctx.workflow.pending_draft_id = None
    await save_context(ctx)
