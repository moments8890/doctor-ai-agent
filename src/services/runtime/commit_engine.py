"""Commit engine — durable writes for the UEC pipeline (ADR 0012 §5c).

Receives a fully resolved action from resolve and executes the write.
Never fails on binding — that was already validated by resolve.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError

from messages import M
from services.runtime.types import (
    ActionType,
    CommitResult,
    CreatePatientArgs,
    ResolvedAction,
    ScheduleTaskArgs,
    TaskType,
)
from utils.log import log


TASK_TYPE_LABELS: Dict[str, str] = {
    "appointment": "复诊预约",
    "follow_up": "随访任务",
    "general": "任务",
}


async def commit(
    action: ResolvedAction,
    ctx: Any,  # DoctorCtx — avoid circular import
    recent_turns: Optional[List[dict]] = None,
    user_input: str = "",
) -> CommitResult:
    """Execute a durable write action. Returns CommitResult for compose."""
    at = action.action_type

    if at == ActionType.select_patient:
        return await _select_patient(action, ctx)
    if at == ActionType.create_patient:
        return await _create_patient(action, ctx)
    if at == ActionType.schedule_task:
        return await _schedule_task(action, ctx)
    if at == ActionType.create_draft:
        return await _create_draft(action, ctx, recent_turns or [], user_input)

    log.error("[commit] unknown action type: %s", at)
    return CommitResult(status="error", error_key="execute_error")


# ---------------------------------------------------------------------------
# select_patient
# ---------------------------------------------------------------------------

async def _select_patient(action: ResolvedAction, ctx: Any) -> CommitResult:
    """Bind context to the resolved patient."""
    # Resolve already found the patient — just update context
    _switch_context(ctx, action.patient_id, action.patient_name)
    log.info("[commit] select_patient=%s id=%s doctor=%s",
             action.patient_name, action.patient_id, ctx.doctor_id)
    return CommitResult(status="ok")


# ---------------------------------------------------------------------------
# create_patient
# ---------------------------------------------------------------------------

async def _create_patient(action: ResolvedAction, ctx: Any) -> CommitResult:
    """Create a new patient and bind to context."""
    args = action.args
    name = args.patient_name if isinstance(args, CreatePatientArgs) else action.patient_name
    if not name:
        return CommitResult(status="error", error_key="need_patient_name")

    gender = getattr(args, "gender", None)
    age = getattr(args, "age", None)

    from db.crud import create_patient as db_create_patient, find_patient_by_name
    from db.engine import AsyncSessionLocal

    # Check for existing patient first
    async with AsyncSessionLocal() as db:
        existing = await find_patient_by_name(db, ctx.doctor_id, name)
        if existing:
            _switch_context(ctx, existing.id, existing.name)
            log.info("[commit] create_patient: already exists, selected %s", existing.name)
            return CommitResult(
                status="ok",
                data={"existing": True, "name": existing.name},
                message_key="patient_exists_selected",
            )

    # Create new patient — capture scalars inside session to avoid DetachedInstanceError
    async with AsyncSessionLocal() as db:
        try:
            patient, _access_code = await db_create_patient(
                db, ctx.doctor_id, name, gender, age,
            )
            new_id, new_name = patient.id, patient.name
        except IntegrityError:
            log.warning("[commit] create_patient duplicate: %s doctor=%s", name, ctx.doctor_id)
            new_id, new_name = None, None
        except Exception as e:
            log.error("[commit] create_patient FAILED: %s", e, exc_info=True)
            return CommitResult(status="error", error_key="create_patient_failed")

    if new_id is None:
        # IntegrityError path — look up the existing patient
        async with AsyncSessionLocal() as db2:
            dup = await find_patient_by_name(db2, ctx.doctor_id, name)
            if dup is None:
                return CommitResult(status="error", error_key="create_patient_failed")
            new_id, new_name = dup.id, dup.name
        _switch_context(ctx, new_id, new_name)
        return CommitResult(
            status="ok",
            data={"existing": True, "name": new_name},
            message_key="patient_exists_selected",
        )

    _switch_context(ctx, new_id, new_name)
    log.info("[commit] create_patient=%s id=%s doctor=%s", new_name, new_id, ctx.doctor_id)
    return CommitResult(status="ok", data={"name": new_name})


# ---------------------------------------------------------------------------
# schedule_task (immediate commit — no confirmation)
# ---------------------------------------------------------------------------

async def _schedule_task(action: ResolvedAction, ctx: Any) -> CommitResult:
    """Create a DoctorTask row immediately."""
    args = action.args
    if not isinstance(args, ScheduleTaskArgs):
        return CommitResult(status="error", error_key="execute_error")

    from db.engine import AsyncSessionLocal
    from db.repositories.tasks import TaskRepository

    task_type_str = args.task_type or "general"
    task_label = TASK_TYPE_LABELS.get(task_type_str, "任务")
    title = args.title or task_label

    # Parse dates
    scheduled_for_dt = _parse_iso(args.scheduled_for) if args.scheduled_for else None
    remind_at_dt = _parse_iso(args.remind_at) if args.remind_at else None

    # Format display datetime
    dt_display = _format_datetime_display(scheduled_for_dt) if scheduled_for_dt else ""

    try:
        async with AsyncSessionLocal() as db:
            repo = TaskRepository(db)
            task = await repo.create(
                doctor_id=ctx.doctor_id,
                task_type=task_type_str,
                title=title,
                content=args.notes,
                patient_id=action.patient_id,
                record_id=None,
                due_at=scheduled_for_dt,  # use scheduled_for as due_at for existing schema
                scheduled_for=scheduled_for_dt,
                remind_at=remind_at_dt,
            )
            task_id = task.id
    except Exception as e:
        log.error("[commit] schedule_task FAILED: %s", e, exc_info=True)
        return CommitResult(status="error", error_key="execute_error")

    log.info("[commit] schedule_task=%s patient=%s doctor=%s",
             task_id, action.patient_name, ctx.doctor_id)

    # Detect if noon was a default (hour=12, minute=0)
    noon_default = (
        scheduled_for_dt is not None
        and scheduled_for_dt.hour == 12
        and scheduled_for_dt.minute == 0
    )

    return CommitResult(
        status="ok",
        data={
            "task_id": task_id,
            "task_label": task_label,
            "datetime_display": dt_display,
            "patient_name": action.patient_name,
            "noon_default": noon_default,
        },
    )


# ---------------------------------------------------------------------------
# create_draft (requires structuring LLM — ADR 0012 §5c, §15)
# ---------------------------------------------------------------------------

async def _create_draft(
    action: ResolvedAction,
    ctx: Any,
    recent_turns: List[dict],
    user_input: str,
) -> CommitResult:
    """Collect clinical content, structure, create pending draft."""
    patient_name = action.patient_name or ctx.workflow.patient_name or ""
    patient_id = action.patient_id or ctx.workflow.patient_id

    # Collect clinical text from chat_archive (ADR 0012 §8, §17 — no working_note)
    clinical_text = await _collect_clinical_text(ctx.doctor_id, patient_id, recent_turns, user_input)
    if not clinical_text.strip():
        return CommitResult(status="error", error_key="no_clinical_content")

    # Structuring LLM call (2nd LLM call for create_draft turns)
    from services.ai.structuring import structure_medical_record

    try:
        record = await structure_medical_record(clinical_text, doctor_id=ctx.doctor_id)
    except ValueError as e:
        log.warning("[commit] structuring validation error doctor=%s: %s", ctx.doctor_id, e)
        return CommitResult(status="error", error_key="no_clinical_content")
    except Exception as e:
        log.error("[commit] structuring FAILED doctor=%s: %s", ctx.doctor_id, e, exc_info=True)
        return CommitResult(status="error", error_key="structuring_failed")

    # Create pending record
    from db.crud.pending import create_pending_record
    from db.engine import AsyncSessionLocal
    from utils.runtime_config import get_pending_record_ttl_minutes

    draft_ttl = get_pending_record_ttl_minutes()
    draft_id = uuid.uuid4().hex
    draft_data = record.model_dump()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=draft_ttl)

    try:
        async with AsyncSessionLocal() as db:
            await create_pending_record(
                db,
                record_id=draft_id,
                doctor_id=ctx.doctor_id,
                draft_json=json.dumps(draft_data, ensure_ascii=False),
                patient_id=patient_id,
                patient_name=patient_name,
                ttl_minutes=draft_ttl,
            )
    except Exception as e:
        log.error("[commit] draft create FAILED doctor=%s: %s", ctx.doctor_id, e, exc_info=True)
        return CommitResult(status="error", error_key="structuring_failed")

    ctx.workflow.pending_draft_id = draft_id

    content_preview = (record.content or "")[:200]
    if len(record.content or "") > 200:
        content_preview += "..."

    log.info("[commit] draft created id=%s patient=%s doctor=%s", draft_id, patient_name, ctx.doctor_id)
    return CommitResult(
        status="pending_confirmation",
        data={
            "preview": content_preview,
            "patient_name": patient_name,
            "expires_at": expires_at.isoformat(),
        },
        pending_id=draft_id,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _switch_context(ctx: Any, patient_id: Optional[int], patient_name: Optional[str]) -> None:
    """Update workflow context to point at a new patient."""
    ctx.workflow.patient_id = patient_id
    ctx.workflow.patient_name = patient_name


async def _collect_clinical_text(
    doctor_id: str,
    patient_id: Optional[int],
    recent_turns: List[dict],
    user_input: str,
) -> str:
    """Collect clinical content from chat_archive user turns + current input.

    ADR 0012 §8, §17: no working_note dependency. Content comes from
    chat_archive (user turns since last completed record for the patient).
    When patient_id is available, fetches patient-scoped turns from DB.
    Falls back to unscoped recent_turns for pre-migration rows (patient_id=NULL).
    """
    parts: list[str] = []

    if patient_id is not None:
        # Patient-scoped scan from chat_archive (ADR 0012 §8, A2)
        from db.engine import AsyncSessionLocal
        from db.models.doctor import ChatArchive
        from sqlalchemy import select

        try:
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(ChatArchive)
                    .where(
                        ChatArchive.doctor_id == doctor_id,
                        ChatArchive.patient_id == patient_id,
                        ChatArchive.role == "user",
                    )
                    .order_by(ChatArchive.created_at.desc())
                    .limit(30)
                )
                rows = (await db.execute(stmt)).scalars().all()
                for row in reversed(rows):
                    content = (row.content or "").strip()
                    if len(content) > 5:
                        parts.append(content)
        except Exception as e:
            log.warning("[commit] patient-scoped archive scan failed, falling back: %s", e)
            parts = []

    # Fallback: unscoped scan from recent_turns
    if not parts:
        for turn in recent_turns:
            if turn.get("role") == "user" and len(turn.get("content", "").strip()) > 5:
                parts.append(turn["content"].strip())

    if user_input.strip() and user_input.strip() not in parts:
        parts.append(user_input.strip())
    return "\n".join(parts)


def _parse_iso(s: str) -> Optional[datetime]:
    """Parse ISO-8601 string to datetime."""
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError) as e:
        log.warning("[commit] _parse_iso failed for %r: %s", s, e)
        return None


def _format_datetime_display(dt: datetime) -> str:
    """Format datetime for Chinese display, converting to Asia/Shanghai."""
    # Convert to local time if timezone-aware
    try:
        from zoneinfo import ZoneInfo
        local_tz = ZoneInfo("Asia/Shanghai")
        if dt.tzinfo is not None:
            dt = dt.astimezone(local_tz)
    except Exception:
        pass  # best-effort timezone conversion

    month = dt.month
    day = dt.day
    hour = dt.hour
    minute = dt.minute
    min_str = f"{minute}分" if minute != 0 else ""

    if hour == 0:
        time_part = f"凌晨12点{min_str}"
    elif hour < 6:
        time_part = f"凌晨{hour}点{min_str}"
    elif hour < 12:
        time_part = f"上午{hour}点{min_str}"
    elif hour == 12:
        time_part = f"中午12点{min_str}"
    elif hour < 18:
        time_part = f"下午{hour - 12}点{min_str}"
    else:
        time_part = f"晚上{hour - 12}点{min_str}"

    return f"{month}月{day}日{time_part}"
