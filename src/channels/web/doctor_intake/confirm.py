"""Doctor intake — confirm and cancel endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from utils.log import log

from .shared import (
    IntakeConfirmResponse,
    _resolve_doctor_id,
    _verify_session,
    _build_clinical_text,
)

router = APIRouter()

# Lazy singleton — deferred to avoid a circular import chain:
#   engine → templates → medical_general → channels.web.doctor_intake.shared
#   → __init__ → routes → confirm → engine
_ENGINE = None


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        from domain.intake.engine import IntakeEngine
        _ENGINE = IntakeEngine()
    return _ENGINE


# ── POST /confirm ────────────────────────────────────────────────

@router.post("/confirm", response_model=IntakeConfirmResponse)
async def intake_confirm_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    patient_name: Optional[str] = Form(default=None),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Confirm intake and save to medical_records.

    Delegates all business logic (batch re-extraction, patient resolution,
    record insertion, follow-up task generation) to IntakeEngine.confirm().
    The endpoint retains only auth, HTTP guards, and response shaping.
    """
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(
        session_id, resolved_doctor, candidate_doctor_id=doctor_id,
    )

    if session.status not in ("active",):
        raise HTTPException(
            400, f"Session status is '{session.status}', cannot confirm",
        )

    collected = session.collected or {}
    if not any(v for k, v in collected.items() if not k.startswith("_")):
        raise HTTPException(400, "No collected data to confirm")

    ref = await _get_engine().confirm(
        session_id=session.id,
        override_patient_name=(patient_name.strip() if patient_name else None),
    )

    # Build the preview + status from the freshly inserted record.
    # Reading from the persisted row (rather than `collected`) ensures
    # the preview reflects exactly what was saved — closes a latent drift bug.
    from db.models.records import MedicalRecordDB
    record = await db.get(MedicalRecordDB, ref.id)
    preview = _build_clinical_text({
        k: getattr(record, k, None) for k in (
            "chief_complaint", "present_illness", "diagnosis",
            "treatment_plan", "orders_followup",
        )
    }) if record else None

    return IntakeConfirmResponse(
        status=record.status if record else "confirmed",
        preview=(preview[:200] if preview else None),
        pending_id=str(ref.id),
    )


# ── POST /cancel ─────────────────────────────────────────────────

@router.post("/cancel")
async def intake_cancel_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(
        session_id, resolved_doctor, candidate_doctor_id=doctor_id,
    )

    from domain.patients.intake_session import save_session
    from db.models.intake_session import IntakeStatus

    session.status = IntakeStatus.abandoned
    await save_session(session)

    from domain.patients.intake_turn import release_session_lock
    release_session_lock(session_id)

    return {"status": "abandoned"}
