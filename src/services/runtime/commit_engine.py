"""Commit engine — durable writes for the UEC pipeline (ADR 0012 §5c, ADR 0013).

Receives a fully resolved action from resolve and executes the write.
Never fails on binding — that was already validated by resolve.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, List, Optional

from services.runtime.types import (
    ActionType,
    CommitResult,
    ResolvedAction,
    TaskArgs,
    UpdateArgs,
)
from utils.log import log


async def commit(
    action: ResolvedAction,
    ctx: Any,
    recent_turns: Optional[List[dict]] = None,
    user_input: str = "",
) -> CommitResult:
    """Execute a durable write action. Returns CommitResult for compose."""
    at = action.action_type

    if at == ActionType.record:
        return await _create_record(action, ctx, recent_turns or [], user_input)
    if at == ActionType.update:
        return await _update_record(action, ctx)
    if at == ActionType.task:
        return await _schedule_task(action, ctx)

    log(f"[commit] unknown action type: {at}", level="error")
    return CommitResult(status="error", error_key="execute_error")


# ---------------------------------------------------------------------------
# schedule_task (immediate commit — no confirmation)
# ---------------------------------------------------------------------------

async def _schedule_task(action: ResolvedAction, ctx: Any) -> CommitResult:
    """Create a DoctorTask row immediately."""
    args = action.args
    if not isinstance(args, TaskArgs):
        return CommitResult(status="error", error_key="execute_error")

    from db.engine import AsyncSessionLocal
    from db.repositories.tasks import TaskRepository

    task_type_str = "general"
    title = args.title or "任务"

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
        log(f"[commit] schedule_task FAILED: {e}", level="error")
        return CommitResult(status="error", error_key="execute_error")

    log(f"[commit] schedule_task={task_id} patient={action.patient_name} doctor={ctx.doctor_id}")

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
            "title": getattr(action.args, "title", None) or "任务",
            "datetime_display": dt_display,
            "patient_name": action.patient_name,
            "noon_default": noon_default,
        },
    )


# ---------------------------------------------------------------------------
# create_record (direct save — ADR 0012 §5c)
# ---------------------------------------------------------------------------

async def _create_record(
    action: ResolvedAction,
    ctx: Any,
    recent_turns: List[dict],
    user_input: str,
) -> CommitResult:
    """Collect clinical content, structure, and save record directly."""
    patient_name = action.patient_name or ctx.workflow.patient_name or ""
    patient_id = action.patient_id or ctx.workflow.patient_id

    clinical_text = await _collect_clinical_text(ctx.doctor_id, patient_id, recent_turns, user_input)
    if not clinical_text.strip():
        # Demographics-only: patient already created by resolve._ensure_patient
        if not patient_name:
            # Defensive guard — resolve should catch this first
            return CommitResult(status="error", error_key="need_patient_name")
        log(f"[commit] patient-only registration patient={patient_name} doctor={ctx.doctor_id}")
        return CommitResult(
            status="ok",
            data={"patient_only": True, "name": patient_name},
        )

    from services.ai.structuring import structure_medical_record, _NO_CLINICAL_CONTENT
    try:
        record = await structure_medical_record(clinical_text, doctor_id=ctx.doctor_id)
    except ValueError:
        return CommitResult(status="error", error_key="no_clinical_content")
    except Exception as e:
        log(f"[commit] structuring FAILED: {e}", level="error")
        return CommitResult(status="error", error_key="structuring_failed")

    if (record.content or "").strip() == _NO_CLINICAL_CONTENT:
        return CommitResult(status="error", error_key="no_clinical_content")

    from db.crud import save_record
    from db.engine import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            db_record = await save_record(db, ctx.doctor_id, record, patient_id)
            record_id = db_record.id
            if patient_id is not None:
                from services.patient.patient_categorization import recompute_patient_category
                await recompute_patient_category(patient_id, db, commit=False)
            await db.commit()
    except Exception as e:
        log(f"[commit] save_record FAILED: {e}", level="error")
        return CommitResult(status="error", error_key="structuring_failed")

    from services.domain.intent_handlers._confirm_pending import _fire_post_save_tasks
    _fire_post_save_tasks(ctx.doctor_id, record, record_id, patient_name, patient_id)

    content_preview = (record.content or "")[:200]
    if len(record.content or "") > 200:
        content_preview += "..."

    log(f"[commit] record saved id={record_id} patient={patient_name} doctor={ctx.doctor_id}")
    return CommitResult(status="ok", data={"preview": content_preview, "record_id": record_id, "patient_name": patient_name})


# ---------------------------------------------------------------------------
# update_record
# ---------------------------------------------------------------------------

async def _update_record(action: ResolvedAction, ctx: Any) -> CommitResult:
    """Fetch existing record, snapshot, re-structure with amendment, patch."""
    if not isinstance(action.args, UpdateArgs):
        return CommitResult(status="error", error_key="execute_error")
    record_id = action.record_id
    if record_id is None:
        return CommitResult(status="error", error_key="no_record_to_update")
    patient_name = action.patient_name or ctx.workflow.patient_name or ""
    instruction = action.args.instruction

    from db.crud.records import save_record_version
    from db.engine import AsyncSessionLocal
    from db.models import MedicalRecordDB
    from db.repositories.records import RecordRepository
    from services.ai.structuring import structure_medical_record
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Fetch existing
        stmt = select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == ctx.doctor_id,
        ).limit(1)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is None:
            return CommitResult(status="error", error_key="no_record_to_update")

        existing_content = existing.content or ""

        # Snapshot for audit (same session — captures the version we're about to patch)
        try:
            await save_record_version(db, existing, ctx.doctor_id)
        except Exception as e:
            log(f"[commit] save_record_version failed record={record_id}: {e}", level="warning")

        # Re-structure with amendment (LLM call; session stays open)
        combined = f"{existing_content}\n\n---\n医生修改指令：{instruction}"
        try:
            record = await structure_medical_record(combined, doctor_id=ctx.doctor_id)
        except Exception as e:
            log(f"[commit] update structuring FAILED: {e}", level="error")
            return CommitResult(status="error", error_key="structuring_failed")

        # PATCH (same session — no concurrent write can slip in)
        try:
            repo = RecordRepository(db)
            await repo.update(record_id=record_id, doctor_id=ctx.doctor_id, content=record.content, tags=record.tags, structured=record.structured)
            await db.commit()
        except Exception as e:
            log(f"[commit] update_record FAILED: {e}", level="error")
            return CommitResult(status="error", error_key="execute_error")

    content_preview = (record.content or "")[:200]
    if len(record.content or "") > 200:
        content_preview += "..."

    log(f"[commit] record updated id={record_id} patient={patient_name} doctor={ctx.doctor_id}")
    return CommitResult(status="ok", data={"preview": content_preview, "record_id": record_id, "patient_name": patient_name})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLLECT_WINDOW_MINUTES = 30


async def _collect_clinical_text(
    doctor_id: str,
    patient_id: Optional[int],
    recent_turns: List[dict],
    user_input: str,
) -> str:
    """Collect clinical content from chat_archive user turns + current input.

    ADR 0015: dual boundary — only include turns after the later of:
      1) the patient's last saved record timestamp
      2) now - 30 minutes
    This prevents cross-record contamination and stale turn accumulation.
    """
    parts: list[str] = []

    if patient_id is not None:
        from db.engine import AsyncSessionLocal
        from db.models.doctor import ChatArchive
        from db.models import MedicalRecordDB
        from sqlalchemy import select, func

        try:
            async with AsyncSessionLocal() as db:
                # Boundary 1: last saved record timestamp
                last_record_ts = (await db.execute(
                    select(func.max(MedicalRecordDB.created_at)).where(
                        MedicalRecordDB.doctor_id == doctor_id,
                        MedicalRecordDB.patient_id == patient_id,
                    )
                )).scalar()

                # Boundary 2: recency window
                recency_cutoff = datetime.utcnow() - timedelta(minutes=_COLLECT_WINDOW_MINUTES)

                # Effective cutoff: the later of the two
                if last_record_ts and last_record_ts > recency_cutoff:
                    cutoff = last_record_ts
                else:
                    cutoff = recency_cutoff

                stmt = (
                    select(ChatArchive)
                    .where(
                        ChatArchive.doctor_id == doctor_id,
                        ChatArchive.patient_id == patient_id,
                        ChatArchive.role == "user",
                        ChatArchive.created_at > cutoff,
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
            log(f"[commit] patient-scoped archive scan failed, falling back: {e}", level="warning")
            parts = []

    # For new patients with no archive, use only the current user input —
    # unscoped recent_turns may contain other patients' clinical data.
    if user_input.strip() and user_input.strip() not in parts:
        parts.append(user_input.strip())
    return "\n".join(parts)


def _parse_iso(s: str) -> Optional[datetime]:
    """Parse ISO-8601 string to datetime."""
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError) as e:
        log(f"[commit] _parse_iso failed for {s!r}: {e}", level="warning")
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
