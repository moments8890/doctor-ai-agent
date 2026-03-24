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
    conversation: List[Dict[str, Any]] = []


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


# ── GET /session/{session_id} ────────────────────────────────────

@router.get("/session/{session_id}", response_model=DoctorInterviewResponse)
async def get_session_state(
    session_id: str,
    doctor_id: str = "",
    authorization: Optional[str] = Header(default=None),
):
    """Get current session state — used when resuming from chat."""
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor)

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
    """Confirm interview and save collected SOAP fields directly to medical_records.

    No re-structuring LLM call — the interview already collected structured fields.
    Checks completeness: if diagnosis + treatment + followup are filled, saves as
    'completed'. Otherwise saves as 'pending_review'.
    """
    resolved_doctor = await _resolve_doctor_id(doctor_id, authorization)
    session = await _verify_session(session_id, resolved_doctor)

    if session.status not in ("interviewing",):
        raise HTTPException(400, f"Session status is '{session.status}', cannot confirm")

    from domain.patients.interview_session import save_session
    from db.models.interview_session import InterviewStatus

    collected = session.collected or {}
    if not any(collected.values()):
        raise HTTPException(400, "No collected data to confirm")

    # Save directly to medical_records with SOAP columns
    from db.engine import AsyncSessionLocal
    from db.models.records import MedicalRecordDB, RecordStatus
    from db.crud.doctor import _ensure_doctor_exists

    # Build content summary from collected fields
    clinical_text = _build_clinical_text(collected)

    # Determine status based on completeness
    has_diagnosis = bool(collected.get("diagnosis", "").strip())
    has_treatment = bool(collected.get("treatment_plan", "").strip())
    has_followup = bool(collected.get("orders_followup", "").strip())
    status = RecordStatus.completed if (has_diagnosis and has_treatment and has_followup) else RecordStatus.pending_review

    async with AsyncSessionLocal() as db:
        await _ensure_doctor_exists(db, resolved_doctor)
        record = MedicalRecordDB(
            doctor_id=resolved_doctor,
            patient_id=session.patient_id,
            record_type="interview_summary",
            status=status.value,
            content=clinical_text,
            # SOAP fields from collected
            chief_complaint=collected.get("chief_complaint"),
            present_illness=collected.get("present_illness"),
            past_history=collected.get("past_history"),
            allergy_history=collected.get("allergy_history"),
            personal_history=collected.get("personal_history"),
            marital_reproductive=collected.get("marital_reproductive"),
            family_history=collected.get("family_history"),
            physical_exam=collected.get("physical_exam"),
            specialist_exam=collected.get("specialist_exam"),
            auxiliary_exam=collected.get("auxiliary_exam"),
            diagnosis=collected.get("diagnosis"),
            treatment_plan=collected.get("treatment_plan"),
            orders_followup=collected.get("orders_followup"),
        )
        db.add(record)
        await db.commit()
        record_id = record.id

    log(f"[interview-confirm] record saved id={record_id} doctor={resolved_doctor} patient={session.patient_id} status={status.value}")

    # Update session status
    session.status = InterviewStatus.confirmed
    await save_session(session)

    return InterviewConfirmResponse(
        status=status.value,
        preview=clinical_text[:200] if clinical_text else None,
        pending_id=str(record_id),
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
