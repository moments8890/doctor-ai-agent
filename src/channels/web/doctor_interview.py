"""Doctor interview endpoints — structured record collection."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from domain.patients.interview_turn import FIELD_LABELS
from utils.log import log

router = APIRouter(prefix="/api/records/interview", tags=["doctor-interview"])


# ── Pydantic models ──────────────────────────────────────────────

class DoctorInterviewResponse(BaseModel):
    session_id: str
    reply: str
    collected: Dict[str, str] = {}
    progress: Dict[str, int] = {}
    missing: List[str] = []
    missing_required: List[str] = []
    status: str = "interviewing"
    patient_id: Optional[int] = None
    pending_id: Optional[str] = None
    suggestions: List[str] = []


class InterviewConfirmResponse(BaseModel):
    status: str
    preview: Optional[str] = None
    pending_id: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_doctor_id(doctor_id: str, authorization: Optional[str]) -> str:
    return resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )


async def _verify_session(session_id: str, doctor_id: str):
    from domain.patients.interview_session import load_session
    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "Interview session not found")
    if session.doctor_id != doctor_id:
        raise HTTPException(403, "Not your session")
    return session


def _build_clinical_text(collected: Dict[str, str]) -> str:
    parts = []
    for key, label in FIELD_LABELS.items():
        value = collected.get(key, "")
        if value:
            parts.append(f"{label}：{value}")
    return "\n".join(parts)


def _compute_progress(collected):
    from domain.patients.completeness import check_completeness, count_filled, TOTAL_FIELDS
    missing = check_completeness(collected)
    missing_req = [f for f in ("chief_complaint", "present_illness") if not collected.get(f)]
    return {
        "progress": {"filled": count_filled(collected), "total": TOTAL_FIELDS},
        "missing": missing,
        "missing_required": missing_req,
        "status": "ready_for_confirm" if not missing else "interviewing",
    }


async def _extract_file_text(file: UploadFile) -> str:
    content_type = (file.content_type or "").split(";")[0].strip()
    raw = await file.read()
    if content_type.startswith("image/"):
        from infra.llm.vision import extract_text_from_image
        result = await extract_text_from_image(raw)
        return result.get("text", "") if isinstance(result, dict) else str(result)
    elif content_type == "application/pdf" or (file.filename or "").endswith(".pdf"):
        from domain.knowledge.pdf_extract import extract_text_from_pdf_smart
        return extract_text_from_pdf_smart(raw)
    return ""


# ── POST /turn ───────────────────────────────────────────────────

@router.post("/turn", response_model=DoctorInterviewResponse)
async def interview_turn_endpoint(
    text: str = Form(...),
    session_id: Optional[str] = Form(default=None),
    patient_name: Optional[str] = Form(default=None),
    patient_gender: Optional[str] = Form(default=None),
    patient_age: Optional[int] = Form(default=None),
    doctor_id: str = Form(default=""),
    file: Optional[UploadFile] = File(default=None),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor, scope="records.interview")

    extra_text = ""
    if file:
        extra_text = await _extract_file_text(file)
    merged_text = f"{text}\n{extra_text}".strip() if extra_text else text

    if not session_id:
        if not patient_name:
            raise HTTPException(422, "请提供患者姓名")
        return await _first_turn(resolved_doctor, merged_text, patient_name, patient_gender, patient_age)
    else:
        session = await _verify_session(session_id, resolved_doctor)
        return await _continue_turn(session, merged_text)


async def _first_turn(doctor_id, text, patient_name, patient_gender, patient_age):
    from agent.tools.resolve import resolve
    from domain.patients.interview_session import create_session
    from domain.patients.interview_turn import interview_turn

    resolved = await resolve(patient_name, doctor_id, auto_create=True,
                              gender=patient_gender, age=patient_age)
    if "status" in resolved:
        raise HTTPException(422, resolved.get("message", "Patient resolution failed"))

    patient_id = resolved["patient_id"]
    session = await create_session(doctor_id, patient_id, mode="doctor")
    response = await interview_turn(session.id, text)
    progress_info = _compute_progress(response.collected)

    return DoctorInterviewResponse(
        session_id=session.id,
        reply=response.reply,
        collected=response.collected,
        patient_id=patient_id,
        suggestions=response.suggestions or [],
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


# ── POST /confirm ────────────────────────────────────────────────

@router.post("/confirm", response_model=InterviewConfirmResponse)
async def interview_confirm_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor)

    if session.status not in ("interviewing",):
        raise HTTPException(400, f"Session status is '{session.status}', cannot confirm")

    from domain.patients.interview_session import save_session
    from agent.tools.doctor import _create_pending_record
    from db.models.interview_session import InterviewStatus

    clinical_text = _build_clinical_text(session.collected)
    if not clinical_text.strip():
        raise HTTPException(400, "No collected data to confirm")

    # Look up patient name for pending record
    from db.engine import AsyncSessionLocal
    from db.models import Patient
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        patient = (await db.execute(
            select(Patient).where(Patient.id == session.patient_id)
        )).scalar_one_or_none()
    patient_name = patient.name if patient else ""

    result = await _create_pending_record(
        resolved_doctor, session.patient_id, patient_name,
        clinical_text=clinical_text,
    )

    session.status = InterviewStatus.draft_created
    await save_session(session)

    return InterviewConfirmResponse(
        status=result.get("status", "pending_confirmation"),
        preview=result.get("preview"),
        pending_id=result.get("pending_id"),
    )


# ── POST /cancel ─────────────────────────────────────────────────

@router.post("/cancel")
async def interview_cancel_endpoint(
    session_id: str = Form(...),
    doctor_id: str = Form(default=""),
    authorization: Optional[str] = Header(default=None),
):
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor)

    from domain.patients.interview_session import save_session
    from db.models.interview_session import InterviewStatus

    session.status = InterviewStatus.abandoned
    await save_session(session)
    return {"status": "abandoned"}
