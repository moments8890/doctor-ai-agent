"""Doctor interview — shared Pydantic models and helper functions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel

from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from domain.patients.interview_turn import FIELD_LABELS
from utils.log import log


# ── Pydantic models ──────────────────────────────────────────────

class DoctorInterviewResponse(BaseModel):
    session_id: str
    reply: str
    collected: Dict[str, str] = {}
    progress: Dict[str, Any] = {}
    missing: List[str] = []
    missing_required: List[str] = []
    status: str = "interviewing"
    patient_id: Optional[int] = None
    pending_id: Optional[str] = None
    suggestions: List[str] = []
    conversation: List[Dict[str, Any]] = []
    carry_forward: List[Dict[str, str]] = []


class InterviewConfirmResponse(BaseModel):
    status: str
    preview: Optional[str] = None
    pending_id: Optional[str] = None


class FieldUpdateRequest(BaseModel):
    session_id: str
    doctor_id: str = ""
    field: str
    value: str


class CarryForwardConfirmRequest(BaseModel):
    session_id: str
    doctor_id: str = ""
    field: str
    action: str = "confirm"  # "confirm" or "dismiss"


class CarryForwardConfirmResponse(BaseModel):
    status: str
    progress: Dict[str, Any] = {}
    missing: List[str] = []
    missing_required: List[str] = []
    collected: Dict[str, str] = {}


# ── Constants ────────────────────────────────────────────────────

_CARRY_FORWARD_FIELDS = ("allergy_history", "past_history", "family_history", "personal_history")
_SKIP_VALUES = {"无", "不详", ""}


# ── Helpers ──────────────────────────────────────────────────────

async def _resolve_doctor_id(doctor_id: str, authorization: Optional[str]) -> str:
    return resolve_doctor_id_from_auth_or_fallback(
        doctor_id, authorization,
        fallback_env_flag="RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="dev_local",
    )


async def _verify_session(session_id: str, doctor_id: str, *, candidate_doctor_id: str = ""):
    """Load and verify session ownership.

    Checks resolved doctor_id (from JWT) first. If that doesn't match but
    candidate_doctor_id (from request body) does, use that instead — handles
    the case where JWT resolution fell back to a default but the body has
    the correct value.
    """
    from domain.patients.interview_session import load_session
    session = await load_session(session_id)
    if session is None:
        raise HTTPException(404, "Interview session not found")
    if session.doctor_id == doctor_id:
        return session
    # JWT-resolved ID didn't match — check if the body candidate matches
    if candidate_doctor_id and session.doctor_id == candidate_doctor_id.strip():
        log(f"[interview] session matched via candidate_doctor_id={candidate_doctor_id!r} (JWT resolved to {doctor_id!r})")
        return session
    log(f"[interview] session owner mismatch: session.doctor_id={session.doctor_id!r} != resolved={doctor_id!r} candidate={candidate_doctor_id!r}")
    raise HTTPException(403, "Not your session")


def _build_clinical_text(collected: Dict[str, str]) -> str:
    parts = []
    for key, label in FIELD_LABELS.items():
        value = collected.get(key, "")
        if value:
            parts.append(f"{label}：{value}")
    return "\n".join(parts)


def _compute_progress(collected):
    from domain.patients.completeness import check_completeness
    from domain.patients.interview_turn import _build_progress
    missing = check_completeness(collected, mode="doctor")
    missing_req = [f for f in ("chief_complaint", "present_illness") if not collected.get(f)]
    return {
        "progress": _build_progress(collected, mode="doctor"),
        "missing": missing,
        "missing_required": missing_req,
        "status": "ready_for_confirm" if not missing else "interviewing",
    }


async def _load_carry_forward(doctor_id: str, patient_id: Optional[int]) -> List[Dict[str, str]]:
    """Load stable history fields from the patient's latest record for one-tap confirmation."""
    if patient_id is None:
        return []

    from db.engine import AsyncSessionLocal
    from db.models.records import MedicalRecordDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(MedicalRecordDB).where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == doctor_id,
            ).order_by(MedicalRecordDB.created_at.desc()).limit(1)
        )).scalar_one_or_none()

    if row is None or not row.has_structured_data():
        return []

    source_date = row.created_at.strftime("%Y-%m-%d") if row.created_at else ""
    items = []
    for field_key in _CARRY_FORWARD_FIELDS:
        value = (getattr(row, field_key, None) or "").strip()
        if value and value not in _SKIP_VALUES:
            items.append({
                "field": field_key,
                "label": FIELD_LABELS.get(field_key, field_key),
                "value": value,
                "source_date": source_date,
            })
    return items


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
