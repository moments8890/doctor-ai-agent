"""Deterministic commit engine — the only code that writes artifacts (ADR 0011 §10, §11)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.exc import IntegrityError

from messages import M
from services.runtime.models import ActionRequest, DoctorCtx, ModelOutput, TurnResult
from utils.log import log


async def execute_action(
    ctx: DoctorCtx,
    model_output: ModelOutput,
    recent_turns: List[dict],
    *,
    user_input: str = "",
) -> TurnResult:
    """Validate and execute the model's proposed action."""
    ar = model_output.action_request
    if ar is None or ar.type in ("none", "clarify"):
        return TurnResult(reply=model_output.reply)

    if ar.type == "select_patient":
        return await _select_patient(ctx, ar, model_output)
    if ar.type == "create_patient":
        return await _create_patient(ctx, ar, model_output)
    if ar.type == "create_draft":
        return await _create_draft(ctx, model_output, recent_turns, user_input=user_input)
    if ar.type == "create_patient_and_draft":
        return await _create_patient_and_draft(ctx, ar, model_output, recent_turns, user_input=user_input)

    log(f"[commit] unknown action type: {ar.type}")
    return TurnResult(reply=model_output.reply)


# ---------------------------------------------------------------------------
# Patient switching (ADR 0011 §4)
# ---------------------------------------------------------------------------

def _handle_patient_switch(ctx: DoctorCtx, new_name: str) -> Optional[str]:
    """Check for patient switch and reset context if needed.

    Returns warning string when unsaved working_note existed, else None.
    """
    if ctx.workflow.patient_id is None:
        return None
    if ctx.workflow.patient_name == new_name:
        return None

    old_name = ctx.workflow.patient_name or ""

    warning = None
    if ctx.memory.working_note:
        warning = M.unsaved_notes_cleared.format(name=old_name)

    # Reset context on switch
    ctx.workflow.patient_id = None
    ctx.workflow.patient_name = None
    ctx.workflow.pending_draft_id = None
    ctx.memory.candidate_patient = None
    ctx.memory.working_note = None
    ctx.memory.summary = None

    return warning


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

async def _select_patient(
    ctx: DoctorCtx, ar: ActionRequest, model_output: ModelOutput,
) -> TurnResult:
    """Look up patient by name, bind to context."""
    if not ar.patient_name:
        return TurnResult(reply=M.need_patient_name)

    from db.crud import find_patient_by_name
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        patient = await find_patient_by_name(db, ctx.doctor_id, ar.patient_name)

    if patient is None:
        return TurnResult(reply=M.patient_not_found.format(name=ar.patient_name))

    switch_warning = _handle_patient_switch(ctx, patient.name)
    ctx.workflow.patient_id = patient.id
    ctx.workflow.patient_name = patient.name

    reply = model_output.reply
    if switch_warning:
        reply = f"{switch_warning}\n{reply}"

    log(f"[commit] select_patient={patient.name} id={patient.id} doctor={ctx.doctor_id}")
    return TurnResult(reply=reply)


async def _create_patient(
    ctx: DoctorCtx, ar: ActionRequest, model_output: ModelOutput,
) -> TurnResult:
    """Create a new patient and bind to context."""
    if not ar.patient_name:
        return TurnResult(reply=M.need_patient_name)

    from db.crud import create_patient as db_create_patient, find_patient_by_name
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        existing = await find_patient_by_name(db, ctx.doctor_id, ar.patient_name)
        if existing:
            switch_warning = _handle_patient_switch(ctx, existing.name)
            ctx.workflow.patient_id = existing.id
            ctx.workflow.patient_name = existing.name
            reply = M.patient_exists_selected.format(name=existing.name)
            if switch_warning:
                reply = f"{switch_warning}\n{reply}"
            return TurnResult(reply=reply)

    switch_warning = _handle_patient_switch(ctx, ar.patient_name)

    async with AsyncSessionLocal() as db:
        try:
            patient, _access_code = await db_create_patient(
                db, ctx.doctor_id, ar.patient_name,
                ar.patient_gender, ar.patient_age,
            )
        except IntegrityError:
            # Duplicate name race — another request created the same patient
            log(f"[commit] create_patient duplicate: {ar.patient_name} doctor={ctx.doctor_id}")
            async with AsyncSessionLocal() as db2:
                patient = await find_patient_by_name(db2, ctx.doctor_id, ar.patient_name)
            if patient is None:
                return TurnResult(reply=M.create_patient_failed.format(error="duplicate name conflict"))
            ctx.workflow.patient_id = patient.id
            ctx.workflow.patient_name = patient.name
            return TurnResult(reply=M.patient_exists_selected.format(name=patient.name))
        except Exception as e:
            log(f"[commit] create_patient FAILED ({type(e).__name__}): {e}", level="error", exc_info=True)
            return TurnResult(reply=M.create_patient_failed.format(error=str(e)))

    ctx.workflow.patient_id = patient.id
    ctx.workflow.patient_name = patient.name

    reply = model_output.reply
    if switch_warning:
        reply = f"{switch_warning}\n{reply}"

    log(f"[commit] create_patient={patient.name} id={patient.id} doctor={ctx.doctor_id}")
    return TurnResult(reply=reply)


async def _create_draft(
    ctx: DoctorCtx,
    model_output: ModelOutput,
    recent_turns: List[dict],
    *,
    user_input: str = "",
) -> TurnResult:
    """Run structuring step then create pending draft (ADR 0011 §11)."""
    if not ctx.workflow.patient_id:
        return TurnResult(reply=M.need_patient_for_draft)

    patient_name = ctx.workflow.patient_name or ""
    clinical_text = _collect_clinical_text(ctx, recent_turns, user_input=user_input)
    if not clinical_text.strip():
        return TurnResult(reply=M.no_clinical_content)

    # Structuring step
    from services.ai.structuring import structure_medical_record

    try:
        record = await structure_medical_record(clinical_text, doctor_id=ctx.doctor_id)
    except ValueError as e:
        log(f"[commit] structuring validation error doctor={ctx.doctor_id}: {e}", level="warning", exc_info=True)
        return TurnResult(reply=M.no_clinical_content)
    except Exception as e:
        log(f"[commit] structuring FAILED ({type(e).__name__}) doctor={ctx.doctor_id}: {e}", level="error", exc_info=True)
        return TurnResult(reply=M.structuring_failed)

    # Create pending draft
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
                patient_id=ctx.workflow.patient_id,
                patient_name=patient_name,
                ttl_minutes=draft_ttl,
            )
    except IntegrityError as e:
        log(f"[commit] draft create IntegrityError doctor={ctx.doctor_id}: {e}")
        return TurnResult(reply=M.structuring_failed)
    except Exception as e:
        log(f"[commit] draft create FAILED ({type(e).__name__}) doctor={ctx.doctor_id}: {e}", level="error", exc_info=True)
        return TurnResult(reply=M.structuring_failed)

    ctx.workflow.pending_draft_id = draft_id

    content_preview = (record.content or "")[:200]
    if len(record.content or "") > 200:
        content_preview += "…"

    reply = M.draft_created.format(patient=patient_name, preview=content_preview)
    log(f"[commit] draft created id={draft_id} patient={patient_name} doctor={ctx.doctor_id}")
    return TurnResult(
        reply=reply,
        pending_id=draft_id,
        pending_patient_name=patient_name,
        pending_expires_at=expires_at.isoformat(),
    )


async def _create_patient_and_draft(
    ctx: DoctorCtx,
    ar: ActionRequest,
    model_output: ModelOutput,
    recent_turns: List[dict],
    *,
    user_input: str = "",
) -> TurnResult:
    """Bounded composite: create patient then draft (ADR 0011 §8)."""
    create_result = await _create_patient(ctx, ar, model_output)
    if not ctx.workflow.patient_id:
        return create_result

    draft_result = await _create_draft(ctx, model_output, recent_turns, user_input=user_input)

    if draft_result.pending_id:
        reply = M.patient_created_with_draft.format(
            patient=ar.patient_name, draft_reply=draft_result.reply,
        )
        return TurnResult(
            reply=reply,
            pending_id=draft_result.pending_id,
            pending_patient_name=draft_result.pending_patient_name,
            pending_expires_at=draft_result.pending_expires_at,
        )

    return TurnResult(reply=f"{create_result.reply}\n{draft_result.reply}")


def _collect_clinical_text(
    ctx: DoctorCtx, recent_turns: List[dict], *, user_input: str = "",
) -> str:
    """Collect clinical content from working_note + recent user turns + current input."""
    parts: list[str] = []
    if ctx.memory.working_note:
        parts.append(ctx.memory.working_note)
    for turn in recent_turns:
        if turn["role"] == "user" and len(turn["content"].strip()) > 5:
            parts.append(turn["content"].strip())
    if user_input.strip() and user_input.strip() not in parts:
        parts.append(user_input.strip())
    return "\n".join(parts)
