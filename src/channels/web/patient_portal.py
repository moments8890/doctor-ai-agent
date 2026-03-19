"""
患者自助门户 API：患者可查看自己的病历并向医生发送消息。

认证流程：
  患者输入姓名 + 医生 doctor_id + 6 位 access_code → 精确匹配 Patient 表
  → 校验 PBKDF2-SHA256 哈希 → 签发短期 JWT（含 access_code_version）。
  旧患者（access_code 为 NULL）允许仅姓名登录，并在日志中记录 deprecation 警告。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB
from infra.auth.access_code_hash import verify_access_code
from infra.auth.rate_limit import enforce_doctor_rate_limit
from db.crud.patient_message import save_patient_message
from domain.tasks.notifications import send_doctor_notification
from infra.observability.audit import audit
from utils.log import safe_create_task

from channels.web.patient_portal_auth import (
    _DUMMY_HASH,
    _AUTH_FAIL,
    _authenticate_patient,
    _issue_patient_token,
    _lookup_patient_by_name,
    _verify_patient_access_code,
)
from channels.web.patient_portal_registration import registration_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patient", tags=["patient-portal"])
router.include_router(registration_router)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class PatientSessionRequest(BaseModel):
    doctor_id: str
    patient_name: str
    access_code: Optional[str] = None  # Required when patient has an access_code set


class PatientSessionResponse(BaseModel):
    token: str
    patient_id: int
    patient_name: str


class PatientMeResponse(BaseModel):
    patient_id: int
    patient_name: str


class PatientRecordOut(BaseModel):
    id: int
    record_type: str
    content: Optional[str]
    created_at: datetime


class PatientMessageRequest(BaseModel):
    text: str = Field(..., max_length=2000)


class PatientMessageResponse(BaseModel):
    reply: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/session", response_model=PatientSessionResponse)
async def create_patient_session(body: PatientSessionRequest):
    """Patient login: name + doctor_id + access_code.

    Rate-limited to 5 attempts per minute per doctor_id to prevent enumeration.

    - Patient **with** access_code: code MUST be supplied and match the stored hash.
    - Legacy patient (access_code is NULL): name-only login still works but a
      deprecation warning is logged.  Operators should call
      ``POST /api/patient/access-code`` to upgrade legacy patients.
    """
    doctor_id = (body.doctor_id or "").strip()
    patient_name = (body.patient_name or "").strip()
    if not doctor_id or not patient_name:
        raise HTTPException(status_code=422, detail="doctor_id and patient_name are required")

    enforce_doctor_rate_limit(doctor_id, scope="patient_portal.session", max_requests=5)

    patient = await _lookup_patient_by_name(doctor_id, patient_name)
    supplied_code = (body.access_code or "").strip()

    # Always perform hash work to prevent timing side-channel that leaks
    # whether a patient name exists.  verify_access_code is PBKDF2-based
    # and takes ~100 ms; skipping it for missing patients would let an
    # attacker distinguish "name not found" from "wrong code" by latency.
    if patient is None:
        # Burn the same CPU time as a real verification using a well-formed
        # dummy hash so PBKDF2 actually runs (malformed hashes exit early).
        verify_access_code(supplied_code or "000000", _DUMMY_HASH)
        raise HTTPException(status_code=401, detail=_AUTH_FAIL)

    _verify_patient_access_code(patient, supplied_code)

    acv = getattr(patient, "access_code_version", 0)
    token = _issue_patient_token(patient.id, doctor_id, access_code_version=acv)
    logger.info(
        "[PatientPortal] session issued | doctor_id=%s patient_id=%s code_required=%s",
        doctor_id, patient.id, bool(patient.access_code),
    )
    safe_create_task(audit(
        doctor_id, "LOGIN",
        resource_type="patient", resource_id=str(patient.id),
    ))
    return PatientSessionResponse(token=token, patient_id=patient.id, patient_name=patient.name)


@router.get("/me", response_model=PatientMeResponse)
async def get_patient_me(x_patient_token: Optional[str] = Header(default=None)):
    """Return basic identity info for the current patient token."""
    patient = await _authenticate_patient(x_patient_token)
    return PatientMeResponse(patient_id=patient.id, patient_name=patient.name)


@router.get("/records", response_model=list[PatientRecordOut])
async def get_patient_records(x_patient_token: Optional[str] = Header(default=None)):
    """
    Return the patient's own medical records.
    Only exposes: id, record_type, content, created_at.
    Doctor notes, tags, and internal fields are NOT returned.
    """
    patient = await _authenticate_patient(x_patient_token)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MedicalRecordDB)
            .where(MedicalRecordDB.patient_id == patient.id)
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(100)
        )
        records = result.scalars().all()

    safe_create_task(audit(
        "patient", "READ",
        resource_type="patient_records", resource_id=str(patient.id),
    ))
    return [
        PatientRecordOut(
            id=r.id,
            record_type=r.record_type,
            content=r.content,
            created_at=r.created_at,
        )
        for r in records
    ]


@router.post("/message", response_model=PatientMessageResponse)
async def send_patient_message(
    body: PatientMessageRequest,
    x_patient_token: Optional[str] = Header(default=None),
):
    """
    Receive a message from the patient, persist it, and notify the doctor.
    Rate-limited to 10 messages per minute per patient to prevent spam.
    """
    patient = await _authenticate_patient(x_patient_token)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息内容不能为空")

    # Rate-limit patient messages (keyed by patient_id via doctor_id slot).
    enforce_doctor_rate_limit(
        str(patient.id), scope="patient_portal.message", max_requests=10,
    )

    doctor_id = patient.doctor_id
    patient_name = patient.name

    # Persist the inbound message.
    async with AsyncSessionLocal() as db:
        await save_patient_message(
            db,
            patient_id=patient.id,
            doctor_id=doctor_id,
            content=text,
            direction="inbound",
        )

    logger.info(
        "[PatientPortal] message saved | patient_id=%s doctor_id=%s length=%d",
        patient.id, doctor_id, len(text),
    )

    # Notify the doctor (fire-and-forget; failure is logged but not raised).
    preview = text[:60] + ("…" if len(text) > 60 else "")
    notification_text = "患者【{name}】发来消息：{preview}".format(
        name=patient_name, preview=preview,
    )
    safe_create_task(_notify_doctor_safe(doctor_id, notification_text))

    safe_create_task(audit(
        doctor_id, "WRITE",
        resource_type="patient_message", resource_id=str(patient.id),
    ))

    return PatientMessageResponse(reply="您的消息已收到，医生将尽快回复您。")


async def _notify_doctor_safe(doctor_id: str, message: str) -> None:
    """Send notification to doctor, swallowing exceptions to avoid breaking the response."""
    try:
        await send_doctor_notification(doctor_id, message)
    except Exception:
        logger.exception(
            "[PatientPortal] failed to notify doctor_id=%s", doctor_id,
        )


# ---------------------------------------------------------------------------
# Patient file upload (F1.3 — photo/PDF import)
# ---------------------------------------------------------------------------


@router.post("/upload")
async def patient_upload(
    file: UploadFile = File(...),
    x_patient_token: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
):
    """Patient uploads a medical record photo or PDF for Vision LLM extraction."""
    patient = await _authenticate_patient(x_patient_token, authorization)
    file_bytes = await file.read()

    try:
        from domain.records.vision_import import import_medical_record

        result = await import_medical_record(
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            doctor_id=patient.doctor_id,
            patient_id=patient.id,
        )
        return result
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("413:"):
            raise HTTPException(status_code=413, detail=msg[4:])
        if msg.startswith("415:"):
            raise HTTPException(status_code=415, detail=msg[4:])
        raise HTTPException(status_code=422, detail=msg[4:] if ":" in msg else msg)
    except RuntimeError as exc:
        logger.error(f"[PatientUpload] Vision LLM error: {exc}")
        raise HTTPException(status_code=502, detail="文件识别失败，请稍后重试")
