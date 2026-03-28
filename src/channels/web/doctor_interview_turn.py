"""Doctor interview — turn handling endpoints (GET session, POST turn, PATCH field, POST carry-forward-confirm)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form

from infra.auth.rate_limit import enforce_doctor_rate_limit
from domain.patients.interview_turn import FIELD_LABELS
from utils.log import log

from .doctor_interview_shared import (
    DoctorInterviewResponse,
    CarryForwardConfirmRequest,
    CarryForwardConfirmResponse,
    FieldUpdateRequest,
    _resolve_doctor_id,
    _verify_session,
    _compute_progress,
    _load_carry_forward,
    _extract_file_text,
    _CARRY_FORWARD_FIELDS,
)

router = APIRouter()


# ── GET /session/{session_id} ────────────────────────────────────

@router.get("/session/{session_id}", response_model=DoctorInterviewResponse)
async def get_session_state(
    session_id: str,
    doctor_id: str = "",
    authorization: Optional[str] = Header(default=None),
):
    """Get current session state — used when resuming from chat."""
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor, candidate_doctor_id=doctor_id)

    progress_info = _compute_progress(session.collected)
    last_reply = ""
    for turn in reversed(session.conversation or []):
        if turn.get("role") == "assistant":
            last_reply = turn.get("content", "")
            break

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=last_reply or "病历采集中，请继续输入。",
        collected=session.collected,
        patient_id=session.patient_id,
        conversation=session.conversation or [],
        **progress_info,
    )


# ── POST /turn ───────────────────────────────────────────────────

@router.post("/turn", response_model=DoctorInterviewResponse)
async def interview_turn_endpoint(
    text: str = Form(...),
    session_id: Optional[str] = Form(default=None),
    doctor_id: str = Form(default=""),
    patient_id: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor, scope="records.interview")

    extra_text = ""
    if file:
        extra_text = await _extract_file_text(file)
    merged_text = f"{text}\n{extra_text}".strip() if extra_text else text

    # Parse patient_id from form string to int
    resolved_patient_id = int(patient_id) if patient_id and patient_id.isdigit() else None

    if not session_id:
        return await _first_turn(resolved_doctor, merged_text, resolved_patient_id)
    else:
        session = await _verify_session(session_id, resolved_doctor, candidate_doctor_id=doctor_id)
        return await _continue_turn(session, merged_text)


async def _first_turn(doctor_id, text, pre_patient_id=None):
    from agent.tools.resolve import resolve
    from domain.patients.interview_session import create_session, save_session
    from domain.patients.interview_turn import interview_turn

    # If patient pre-selected from frontend, look up name and seed collected
    initial_fields = None
    if pre_patient_id:
        from db.engine import AsyncSessionLocal
        from db.crud.patient import get_patient_for_doctor
        async with AsyncSessionLocal() as db:
            patient = await get_patient_for_doctor(db, doctor_id, pre_patient_id)
        if patient:
            initial_fields = {"_patient_name": patient.name}
            if patient.gender:
                initial_fields["_patient_gender"] = patient.gender
            if patient.year_of_birth:
                from datetime import date
                age = date.today().year - patient.year_of_birth
                initial_fields["_patient_age"] = f"{age}岁"

    session = await create_session(
        doctor_id, patient_id=pre_patient_id, mode="doctor",
        initial_fields=initial_fields,
    )
    response = await interview_turn(session.id, text)

    # Try to resolve patient from LLM-extracted name (only when no pre-selected patient)
    patient_id = pre_patient_id
    carry_forward = []
    if pre_patient_id:
        carry_forward = await _load_carry_forward(doctor_id, pre_patient_id)
    else:
        patient_name = response.patient_name or response.collected.get("_patient_name")
        if patient_name:
            resolved = await resolve(patient_name, doctor_id, auto_create=False)
            if "patient_id" in resolved:
                patient_id = resolved["patient_id"]
                # Reload session to get latest state, then update patient_id
                from domain.patients.interview_session import load_session
                session = await load_session(session.id)
                session.patient_id = patient_id
                await save_session(session)
                carry_forward = await _load_carry_forward(doctor_id, patient_id)

    progress_info = _compute_progress(response.collected)

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=response.reply,
        collected=response.collected,
        patient_id=patient_id,
        suggestions=response.suggestions or [],
        carry_forward=carry_forward,
        **progress_info,
    )


async def _continue_turn(session, text):
    from domain.patients.interview_turn import interview_turn

    response = await interview_turn(session.id, text)
    progress_info = _compute_progress(response.collected)

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=response.reply,
        collected=response.collected,
        patient_id=session.patient_id,
        suggestions=response.suggestions or [],
        **progress_info,
    )


# ── PATCH /field ─────────────────────────────────────────────────

@router.patch("/field", response_model=DoctorInterviewResponse)
async def update_interview_field(
    body: FieldUpdateRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Update a single field value in an interview session (for inline-edit)."""
    resolved_doctor = await _resolve_doctor_id(body.doctor_id, authorization)
    session = await _verify_session(body.session_id, resolved_doctor, candidate_doctor_id=body.doctor_id)

    # Validate field name
    if body.field not in FIELD_LABELS:
        raise HTTPException(status_code=422, detail=f"Unknown field: {body.field}")

    # Update the field
    session.collected[body.field] = body.value
    from domain.patients.interview_session import save_session
    await save_session(session)

    # Return updated progress
    progress_info = _compute_progress(session.collected)
    return DoctorInterviewResponse(
        session_id=session.id,
        reply="",
        collected=session.collected,
        patient_id=session.patient_id,
        **progress_info,
    )


# ── POST /carry-forward-confirm ──────────────────────────────────

@router.post("/carry-forward-confirm", response_model=CarryForwardConfirmResponse)
async def carry_forward_confirm_endpoint(
    body: CarryForwardConfirmRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Confirm or dismiss a carry-forward field — no LLM round-trip needed."""
    resolved_doctor = await _resolve_doctor_id(body.doctor_id, authorization)
    session = await _verify_session(body.session_id, resolved_doctor, candidate_doctor_id=body.doctor_id)

    if body.field not in _CARRY_FORWARD_FIELDS:
        raise HTTPException(422, f"Field '{body.field}' is not a carry-forward field")

    if body.action == "confirm":
        # Load the value from the patient's latest record
        carry_items = await _load_carry_forward(resolved_doctor, session.patient_id)
        matched = next((item for item in carry_items if item["field"] == body.field), None)
        if matched is None:
            raise HTTPException(404, f"No carry-forward value found for '{body.field}'")

        from domain.patients.interview_session import save_session
        session.collected[body.field] = matched["value"]
        await save_session(session)
        log(f"[carry-forward] confirmed {body.field}='{matched['value'][:30]}' session={body.session_id}")
    else:
        log(f"[carry-forward] dismissed {body.field} session={body.session_id}")

    progress_info = _compute_progress(session.collected)
    return CarryForwardConfirmResponse(
        collected=session.collected,
        **progress_info,
    )
