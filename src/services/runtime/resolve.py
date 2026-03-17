"""Resolve phase: patient lookup, binding, validation (ADR 0012 §5a, §10; ADR 0013).

Resolve takes an ActionIntent and DoctorCtx and produces a fully bound
ResolvedAction or a Clarification.  It is the only code that does patient DB
lookup in the pipeline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Union

from services.runtime.types import (
    ActionIntent,
    ActionType,
    Clarification,
    ClarificationKind,
    ResolvedAction,
)
from utils.log import log


async def resolve(
    action: ActionIntent,
    ctx: Any,  # DoctorCtx — avoid circular import
) -> Union[ResolvedAction, Clarification]:
    """Bind raw understand output to concrete patient/args or clarify."""
    at = action.action_type

    if at == ActionType.none:
        return ResolvedAction(action_type=at, args=action.args)

    # query: unscoped targets skip patient resolution
    if at == ActionType.query:
        target = _get_query_target(action)
        if target in ("patients", "tasks"):
            return ResolvedAction(action_type=at, args=action.args)
        # target=records: resolve patient
        return await _resolve_patient_scoped(action, ctx)

    # record: resolve patient (auto-create if not found)
    if at == ActionType.record:
        pid, pname = await _ensure_patient(action, ctx)
        if pid is None:
            return Clarification(
                kind=ClarificationKind.missing_field,
                missing_fields=["patient_name"],
                message_key="need_patient_for_draft",
            )
        return ResolvedAction(
            action_type=at, patient_id=pid, patient_name=pname,
            args=action.args,
        )

    # update: resolve patient + fetch latest record
    if at == ActionType.update:
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
        record_id, _ = latest
        return ResolvedAction(
            action_type=at, patient_id=pid, patient_name=pname,
            args=action.args, record_id=record_id,
        )

    # task: validate dates + resolve patient
    if at == ActionType.task:
        date_err = _validate_task_dates(action.args)
        if date_err:
            return date_err
        return await _resolve_patient_scoped(action, ctx)

    log(f"[resolve] unknown action type: {at}", level="error")
    return Clarification(kind=ClarificationKind.unsupported)


# ── Helper: query target extraction ─────────────────────────────────────────


def _get_query_target(action: ActionIntent) -> str:
    """Extract query target from args, default to 'records'."""
    if action.args and hasattr(action.args, "target") and action.args.target:
        return action.args.target
    return "records"


# ── Helper: generic patient-scoped resolution ────────────────────────────────


async def _resolve_patient_scoped(
    action: ActionIntent,
    ctx: Any,
) -> Union[ResolvedAction, Clarification]:
    """Generic patient resolution for patient-scoped actions."""
    patient_name: Optional[str] = None
    if action.args and hasattr(action.args, "patient_name"):
        patient_name = action.args.patient_name

    if patient_name:
        match = await _match_patient(patient_name, ctx.doctor_id)
        if isinstance(match, Clarification):
            return match
        pid, pname = match
    elif ctx.workflow.patient_id is not None:
        pid = ctx.workflow.patient_id
        pname = ctx.workflow.patient_name or ""
    else:
        return Clarification(
            kind=ClarificationKind.missing_field,
            missing_fields=["patient_name"],
            message_key="clarify_missing_field",
        )

    return ResolvedAction(
        action_type=action.action_type,
        patient_id=pid,
        patient_name=pname,
        args=action.args,
    )


# ── Helper: task date validation ─────────────────────────────────────────────


def _validate_task_dates(args: Any) -> Optional[Clarification]:
    """Validate scheduled_for / remind_at: not past, not >1 year, valid ISO."""
    now = datetime.now(timezone.utc)
    for field_name in ("scheduled_for", "remind_at"):
        val = getattr(args, field_name, None)
        if val is None:
            continue
        try:
            dt = datetime.fromisoformat(val)
            # LLMs typically omit timezone — treat naive datetimes as UTC
            # so comparison with aware `now` does not raise TypeError.
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
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


# ── Patient ensure (auto-create for record/update) ──────────────────────────


async def _ensure_patient(
    action: ActionIntent,
    ctx: Any,
) -> tuple:
    """Ensure a patient is bound for patient-scoped actions.

    Resolution order:
    1. patient_name from action args → lookup or auto-create
    2. Current context patient (fallback when no name given)
    3. (None, None) if no patient can be resolved

    Returns (patient_id, patient_name) or (None, None).
    """
    # 1. Extract patient_name from args — explicit name always wins
    name: Optional[str] = None
    if action.args and hasattr(action.args, "patient_name"):
        name = action.args.patient_name

    if not name:
        # 2. Fallback to context patient
        if ctx.workflow.patient_id is not None:
            return (ctx.workflow.patient_id, ctx.workflow.patient_name)
        return (None, None)

    # 2b. Validate that the extracted name looks like a person name
    from utils.chinese_names import looks_like_chinese_name
    if not looks_like_chinese_name(name):
        log(f"[resolve] rejected non-name patient_name='{name}' for {action.action_type.value}")
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
                gender = getattr(action.args, "gender", None)
                age = getattr(action.args, "age", None)
                patient, _ = await db_create_patient(db, ctx.doctor_id, name, gender, age)
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
