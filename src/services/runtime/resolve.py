"""Resolve phase: patient lookup, binding, validation (ADR 0012 §5a, §10).

Resolve takes an ActionIntent and DoctorCtx and produces a fully bound
ResolvedAction or a Clarification.  It is the only code that does patient DB
lookup in the pipeline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Union

from services.runtime.types import (
    READ_ACTIONS,
    WRITE_ACTIONS,
    ActionIntent,
    ActionType,
    Clarification,
    ClarificationKind,
    QueryRecordsArgs,
    ResolvedAction,
    ScheduleTaskArgs,
    TaskType,
    UpdateRecordArgs,
)
from utils.log import log


async def resolve(
    action: ActionIntent,
    ctx: Any,  # DoctorCtx — avoid circular import
) -> Union[ResolvedAction, Clarification]:
    """Bind raw understand output to concrete patient/args or clarify."""
    action_type = action.action_type

    if action_type == ActionType.none:
        return ResolvedAction(action_type=action_type, args=action.args)

    # ── list_patients / list_tasks: unscoped, always allowed ────────────
    if action_type in (ActionType.list_patients, ActionType.list_tasks):
        return ResolvedAction(
            action_type=action_type,
            args=action.args,
            scoped_only=True,
        )

    # ── Extract patient_name from args ──────────────────────────────────
    patient_name: Optional[str] = None
    if action.args and hasattr(action.args, "patient_name"):
        patient_name = action.args.patient_name

    # ── Patient resolution ──────────────────────────────────────────────
    is_read = action_type in READ_ACTIONS
    is_write = action_type in WRITE_ACTIONS

    # create_patient doesn't need an existing patient
    if action_type == ActionType.create_patient:
        return ResolvedAction(
            action_type=action_type,
            patient_name=patient_name,
            args=action.args,
        )

    # create_record requires a bound patient — auto-resolve from args if needed
    if action_type == ActionType.create_record:
        pid, pname = await _ensure_patient(action, ctx)
        if pid is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                missing_fields=["patient_name"],
                message_key="need_patient_for_draft",
            )
        return ResolvedAction(
            action_type=action_type,
            patient_id=pid,
            patient_name=pname,
            args=action.args,
        )

    # update_record requires a bound patient + existing record
    if action_type == ActionType.update_record:
        pid, pname = await _ensure_patient(action, ctx)
        if pid is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                missing_fields=["patient_name"],
                message_key="need_patient_for_draft",
            )
        latest = await _fetch_latest_record(pid, ctx.doctor_id)
        if latest is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                message_key="no_record_to_update",
            )
        record_id, _content = latest
        return ResolvedAction(
            action_type=action_type,
            patient_id=pid,
            patient_name=pname,
            args=action.args,
            record_id=record_id,
        )

    # For remaining actions, resolve patient
    if patient_name:
        match_result = await _match_patient(patient_name, ctx.doctor_id)
        if isinstance(match_result, Clarification):
            return match_result
        patient_id, resolved_name = match_result
    elif ctx.workflow.patient_id is not None:
        # Context fallback
        patient_id = ctx.workflow.patient_id
        resolved_name = ctx.workflow.patient_name or ""
    else:
        return Clarification(
            kind=ClarificationKind.missing_field,
            missing_fields=["patient_name"],
            message_key="clarify_missing_field",
        )

    # ── Action-specific validation ──────────────────────────────────────
    if action_type == ActionType.schedule_task:
        validation = _validate_schedule_task(action.args)
        if validation is not None:
            return validation

    return ResolvedAction(
        action_type=action_type,
        patient_id=patient_id,
        patient_name=resolved_name,
        args=action.args,
        scoped_only=is_read,
    )


async def _ensure_patient(
    action: ActionIntent,
    ctx: Any,
) -> tuple:
    """Ensure a patient is bound for patient-scoped actions.

    Resolution order:
    1. Current context patient (already selected)
    2. patient_name from action args → lookup or auto-create
    3. (None, None) if no patient can be resolved

    Returns (patient_id, patient_name) or (None, None).
    """
    # 1. Already have a context patient
    if ctx.workflow.patient_id is not None:
        return (ctx.workflow.patient_id, ctx.workflow.patient_name)

    # 2. Extract patient_name from args
    name: Optional[str] = None
    if action.args and hasattr(action.args, "patient_name"):
        name = action.args.patient_name

    if not name:
        return (None, None)

    # 3. Try to find existing patient
    match = await _match_patient(name, ctx.doctor_id)
    if not isinstance(match, Clarification):
        patient_id, resolved_name = match
        # Bind to context so subsequent actions see the patient
        ctx.workflow.patient_id = patient_id
        ctx.workflow.patient_name = resolved_name
        return (patient_id, resolved_name)

    # 4. Not found → auto-create
    if match.kind in (ClarificationKind.not_found,):
        from db.crud import create_patient as db_create_patient
        from db.engine import AsyncSessionLocal

        try:
            async with AsyncSessionLocal() as db:
                patient, _ = await db_create_patient(db, ctx.doctor_id, name, None, None)
                new_id, new_name = patient.id, patient.name
            ctx.workflow.patient_id = new_id
            ctx.workflow.patient_name = new_name
            log(f"[resolve] auto-created patient '{new_name}' id={new_id} for {action.action_type.value}")
            return (new_id, new_name)
        except Exception as e:
            log(f"[resolve] auto-create patient failed: {e}", level="error")
            return (None, None)

    # Ambiguous or other clarification — can't auto-resolve
    return (None, None)


# ── Latest record lookup ────────────────────────────────────────────────────


async def _fetch_latest_record(
    patient_id: int,
    doctor_id: str,
) -> Optional[tuple]:
    """Pure read — SELECT latest medical_record for patient. Returns (record_id, content) or None."""
    from db.engine import AsyncSessionLocal
    from db.models import MedicalRecordDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        stmt = (
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.doctor_id == doctor_id,
                MedicalRecordDB.patient_id == patient_id,
            )
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return (record.id, record.content)


# ── Patient matching (ADR 0012 §10) ────────────────────────────────────────


async def _match_patient(
    name: str,
    doctor_id: str,
) -> Union[tuple, Clarification]:
    """Two-step lookup: exact match first, prefix fallback.

    Returns (patient_id, patient_name) on success, Clarification on failure.
    """
    from db.engine import AsyncSessionLocal
    from db.models import Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Step 1: exact match
        stmt = select(Patient).where(
            Patient.doctor_id == doctor_id,
            Patient.name == name,
        ).limit(1)
        result = await db.execute(stmt)
        patient = result.scalar_one_or_none()
        if patient is not None:
            return (patient.id, patient.name)

        # Step 2: prefix fallback (min 2 chars)
        if len(name) < 2:
            return Clarification(
                kind=ClarificationKind.not_found,
                message_key="clarify_not_found",
                searched_name=name,
            )

        stmt = select(Patient).where(
            Patient.doctor_id == doctor_id,
            Patient.name.startswith(name),
        ).limit(6)  # cap + 1 to detect overflow
        result = await db.execute(stmt)
        matches: List[Patient] = list(result.scalars().all())

        if len(matches) == 0:
            return Clarification(
                kind=ClarificationKind.not_found,
                message_key="clarify_not_found",
                searched_name=name,
            )
        if len(matches) == 1:
            return (matches[0].id, matches[0].name)
        if len(matches) > 5:
            return Clarification(
                kind=ClarificationKind.not_found,
                message_key="clarify_not_found_too_many",
                searched_name=name,
            )
        # 2-5 matches: ambiguous
        return Clarification(
            kind=ClarificationKind.ambiguous_patient,
            options=[{"name": p.name, "id": p.id} for p in matches],
            message_key="clarify_ambiguous_patient",
        )


# ── Schedule task validation (ADR 0012 §12) ────────────────────────────────


def _validate_schedule_task(args: Any) -> Optional[Clarification]:
    """Validate schedule_task args. Returns Clarification on failure, None on success."""
    if not isinstance(args, ScheduleTaskArgs):
        return Clarification(
            kind=ClarificationKind.missing_field,
            missing_fields=["task_type"],
        )

    # Validate task_type
    if args.task_type:
        try:
            TaskType(args.task_type)
        except ValueError:
            return Clarification(
                kind=ClarificationKind.missing_field,
                missing_fields=["task_type"],
            )
    else:
        return Clarification(
            kind=ClarificationKind.missing_field,
            missing_fields=["task_type"],
        )

    # For appointments, scheduled_for is required (ADR 0012 §8)
    if args.task_type == TaskType.appointment.value and not args.scheduled_for:
        return Clarification(
            kind=ClarificationKind.missing_field,
            missing_fields=["scheduled_for"],
        )

    # Validate dates (resolve validates, does not normalise)
    now = datetime.now(timezone.utc)
    for field_name in ("scheduled_for", "remind_at"):
        val = getattr(args, field_name, None)
        if val is None:
            continue
        try:
            dt = datetime.fromisoformat(val)
            if dt.tzinfo is None:
                # Assume Asia/Shanghai if naive
                pass
            if dt < now - timedelta(minutes=5):
                return Clarification(
                    kind=ClarificationKind.invalid_time,
                    message_key="clarify_invalid_time",
                )
            if dt > now + timedelta(days=366):
                return Clarification(
                    kind=ClarificationKind.invalid_time,
                    message_key="clarify_invalid_time",
                )
        except (ValueError, TypeError):
            return Clarification(
                kind=ClarificationKind.invalid_time,
                message_key="clarify_invalid_time",
            )

    return None
