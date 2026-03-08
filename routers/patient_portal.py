"""
患者自助门户 API：患者可查看自己的病历并向医生发送消息。

认证流程（MVP）：
  患者输入姓名 + 医生 doctor_id → 模糊匹配 Patient 表 → 签发短期 JWT。

TODO: 升级为真实的访问码（6 位 access_code 存储在 Patient 表），
      或接入手机号 OTP，避免纯姓名匹配的身份假冒风险。
"""

from __future__ import annotations

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

@router.post("/session", response_model=PatientSessionResponse)
async def create_patient_session(body: PatientSessionRequest):
    """
    MVP login: fuzzy-match patient by name under the given doctor_id.

    TODO: Replace name-only matching with a proper access_code or OTP flow
          before exposing to real patients in production.
    """
    doctor_id = (body.doctor_id or "").strip()
    patient_name = (body.patient_name or "").strip()
    if not doctor_id or not patient_name:
        raise HTTPException(status_code=422, detail="doctor_id and patient_name are required")

    async with AsyncSessionLocal() as db:
        # Exact-name match first; fall back to prefix match for common short names.
        result = await db.execute(
            select(Patient)
            .where(
                Patient.doctor_id == doctor_id,
                Patient.name == patient_name,
            )
            .limit(1)
        )
        patient = result.scalar_one_or_none()

        if patient is None:
            # Try case-insensitive prefix match (handles nickname vs. full name)
            result = await db.execute(
                select(Patient)
                .where(
                    Patient.doctor_id == doctor_id,
                    Patient.name.ilike(f"{patient_name}%"),
                )
                .limit(1)
            )
            patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(status_code=404, detail="未找到匹配的患者，请确认姓名和医生编号。")

    token = _issue_patient_token(patient.id)
    logger.info(
        "[PatientPortal] session issued | doctor_id=%s patient_id=%s",
        doctor_id, patient.id,
    )
    return PatientSessionResponse(
        token=token,
        patient_id=patient.id,
        patient_name=patient.name,
    )


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
