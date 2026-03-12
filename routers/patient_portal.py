"""
患者自助门户 API：患者可查看自己的病历并向医生发送消息。

认证流程：
  患者输入姓名 + 医生 doctor_id + 6 位 access_code → 精确匹配 Patient 表
  → 校验 PBKDF2-SHA256 哈希 → 签发短期 JWT。
  旧患者（access_code 为 NULL）允许仅姓名登录，并在日志中记录 deprecation 警告。
"""

from __future__ import annotations

import asyncio
import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Patient, MedicalRecordDB
from services.auth.access_code_hash import verify_access_code
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.observability.audit import audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patient", tags=["patient-portal"])


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

_TOKEN_TTL = 86400 * 7  # 7 days


def _portal_secret() -> str:
    secret = os.environ.get("PATIENT_PORTAL_SECRET", "").strip()
    if not secret:
        env = os.environ.get("APP_ENV", "").strip().lower()
        if env in {"production", "prod"}:
            raise RuntimeError(
                "PATIENT_PORTAL_SECRET must be set in production."
            )
        secret = "dev-patient-secret"
    return secret


def _issue_patient_token(patient_id: int) -> str:
    now = int(time.time())
    payload = {
        "patient_id": patient_id,
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    return jwt.encode(payload, _portal_secret(), algorithm="HS256")


def _verify_patient_token(token: str) -> int:
    """Verify JWT and return patient_id, or raise HTTPException."""
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing patient token")
    try:
        payload = jwt.decode(token, _portal_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Patient token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid patient token")

    patient_id = payload.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=401, detail="Token missing patient_id")
    return int(patient_id)


def _parse_patient_token_header(x_patient_token: Optional[str]) -> int:
    """Extract and validate the X-Patient-Token header."""
    if not x_patient_token:
        raise HTTPException(status_code=401, detail="X-Patient-Token header required")
    return _verify_patient_token(x_patient_token)


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
    text: str


class PatientMessageResponse(BaseModel):
    reply: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_AUTH_FAIL = "姓名、医生编号或访问码不正确，请重新确认。"


async def _lookup_patient_by_name(doctor_id: str, patient_name: str) -> "Patient | None":
    """Exact-name lookup of a patient within a doctor's namespace."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Patient)
            .where(Patient.doctor_id == doctor_id, Patient.name == patient_name)
            .limit(1)
        )
        return result.scalar_one_or_none()


def _verify_patient_access_code(patient: "Patient", supplied_code: str) -> None:
    """Validate the access code, with backward-compat for legacy patients.

    - Patient **has** an access_code hash → supplied code must match.
    - Patient has **no** access_code (legacy / NULL) → allow name-only login
      but emit a deprecation warning so operators can migrate.
    """
    if not patient.access_code:
        # Legacy patient — no access code configured yet.
        logger.warning(
            "[PatientPortal] DEPRECATION: name-only login for patient_id=%s "
            "(no access_code set). Migrate this patient to access-code auth.",
            patient.id,
        )
        return
    if not supplied_code or not verify_access_code(supplied_code, patient.access_code):
        raise HTTPException(status_code=401, detail=_AUTH_FAIL)


@router.post("/session", response_model=PatientSessionResponse)
async def create_patient_session(body: PatientSessionRequest):
    """Patient login: name + doctor_id + access_code.

    Rate-limited to 5 attempts per minute per doctor_id to prevent enumeration.

    - Patient **with** access_code: code MUST be supplied and match the stored hash.
    - Legacy patient (access_code is NULL): name-only login still works but a
      deprecation warning is logged.  Operators should call
      ``set_patient_access_code`` to upgrade legacy patients.
    """
    doctor_id = (body.doctor_id or "").strip()
    patient_name = (body.patient_name or "").strip()
    if not doctor_id or not patient_name:
        raise HTTPException(status_code=422, detail="doctor_id and patient_name are required")

    enforce_doctor_rate_limit(doctor_id, scope="patient_portal.session", max_requests=5)

    patient = await _lookup_patient_by_name(doctor_id, patient_name)
    if patient is None:
        raise HTTPException(status_code=401, detail=_AUTH_FAIL)

    _verify_patient_access_code(patient, (body.access_code or "").strip())

    token = _issue_patient_token(patient.id)
    logger.info(
        "[PatientPortal] session issued | doctor_id=%s patient_id=%s code_required=%s",
        doctor_id, patient.id, bool(patient.access_code),
    )
    asyncio.ensure_future(audit(
        doctor_id, "LOGIN",
        resource_type="patient", resource_id=str(patient.id),
    ))
    return PatientSessionResponse(token=token, patient_id=patient.id, patient_name=patient.name)


@router.get("/me", response_model=PatientMeResponse)
async def get_patient_me(x_patient_token: Optional[str] = Header(default=None)):
    """Return basic identity info for the current patient token."""
    patient_id = _parse_patient_token_header(x_patient_token)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Patient).where(Patient.id == patient_id).limit(1)
        )
        patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    return PatientMeResponse(patient_id=patient.id, patient_name=patient.name)


@router.get("/records", response_model=list[PatientRecordOut])
async def get_patient_records(x_patient_token: Optional[str] = Header(default=None)):
    """
    Return the patient's own medical records.
    Only exposes: id, record_type, content, created_at.
    Doctor notes, tags, and internal fields are NOT returned.
    """
    patient_id = _parse_patient_token_header(x_patient_token)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MedicalRecordDB)
            .where(MedicalRecordDB.patient_id == patient_id)
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(100)
        )
        records = result.scalars().all()

    asyncio.ensure_future(audit(
        "patient", "READ",
        resource_type="patient_records", resource_id=str(patient_id),
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
    Receive a message from the patient.

    MVP: logs the message and returns a static acknowledgement.
    TODO: Persist to a PatientMessage table and notify the doctor.
    """
    patient_id = _parse_patient_token_header(x_patient_token)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="消息内容不能为空")

    logger.info(
        "[PatientPortal] message received | patient_id=%s length=%d",
        patient_id, len(text),
    )

    # TODO: Save to PatientMessage table and push notification to doctor.
    return PatientMessageResponse(reply="您的消息已收到，医生将尽快回复您。")
