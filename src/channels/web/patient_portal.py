"""
患者自助门户 API：患者可查看自己的病历并向医生发送消息。

认证流程：
  患者输入姓名 + 医生 doctor_id + 6 位 access_code → 精确匹配 Patient 表
  → 校验 PBKDF2-SHA256 哈希 → 签发短期 JWT（含 access_code_version）。
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
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Patient, MedicalRecordDB
from db.crud.patient_message import save_patient_message
from services.auth.access_code_hash import hash_access_code, verify_access_code
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.notify.notification import send_doctor_notification
from services.observability.audit import audit
from utils.log import safe_create_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/patient", tags=["patient-portal"])

# Pre-computed PBKDF2 hash of "000000" used as a timing-equaliser when
# the patient lookup misses.  Generated once at import time.
_DUMMY_HASH: str = hash_access_code("000000")


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

_TOKEN_TTL = 86400  # 24 hours


def _portal_secret() -> str:
    secret = os.environ.get("PATIENT_PORTAL_SECRET", "").strip()
    if not secret:
        from services.auth import is_production
        if is_production():
            raise RuntimeError(
                "PATIENT_PORTAL_SECRET must be set in production."
            )
        secret = "dev-patient-secret"
    return secret


_PATIENT_TOKEN_AUD = "patient_portal"


def _issue_patient_token(
    patient_id: int, doctor_id: str, access_code_version: int = 0,
) -> str:
    now = int(time.time())
    payload = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "acv": access_code_version,
        "aud": _PATIENT_TOKEN_AUD,
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    return jwt.encode(payload, _portal_secret(), algorithm="HS256")


def _verify_patient_token(token: str) -> dict:
    """Verify JWT and return decoded payload dict, or raise HTTPException.

    The caller must check ``acv`` against the patient's current
    ``access_code_version`` to ensure the token hasn't been revoked by
    an access-code rotation.
    """
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing patient token")
    try:
        payload = jwt.decode(
            token, _portal_secret(), algorithms=["HS256"],
            audience=_PATIENT_TOKEN_AUD,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Patient token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid patient token")

    patient_id = payload.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=401, detail="Token missing patient_id")
    return {
        "patient_id": int(patient_id),
        "doctor_id": payload.get("doctor_id"),
        "acv": payload.get("acv", 0),
    }


async def _authenticate_patient(x_patient_token: Optional[str]) -> Patient:
    """Validate X-Patient-Token header, load patient, and enforce acv check.

    Returns the Patient ORM instance on success; raises HTTPException otherwise.
    """
    if not x_patient_token:
        raise HTTPException(status_code=401, detail="X-Patient-Token header required")
    claims = _verify_patient_token(x_patient_token)
    patient_id = claims["patient_id"]
    token_doctor_id = claims.get("doctor_id")
    token_acv = claims["acv"]

    async with AsyncSessionLocal() as db:
        stmt = select(Patient).where(Patient.id == patient_id)
        if token_doctor_id:
            stmt = stmt.where(Patient.doctor_id == token_doctor_id)
        result = await db.execute(stmt.limit(1))
        patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Reject tokens issued before the most recent access-code rotation.
    if token_acv != getattr(patient, "access_code_version", 0):
        raise HTTPException(status_code=401, detail="Token revoked — please log in again")

    return patient


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
        # Reject login: name-only auth is too weak for medical data.
        logger.warning(
            "[PatientPortal] BLOCKED: name-only login for patient_id=%s "
            "(no access_code set). Migrate this patient via POST /api/patient/access-code.",
            patient.id,
        )
        raise HTTPException(
            status_code=403,
            detail="该患者尚未设置访问码，请联系您的医生获取访问码。",
        )
    if not supplied_code or not verify_access_code(supplied_code, patient.access_code):
        raise HTTPException(status_code=401, detail=_AUTH_FAIL)


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


# ---------------------------------------------------------------------------
# Access-code management (doctor-facing)
# ---------------------------------------------------------------------------

class AccessCodeResetRequest(BaseModel):
    doctor_id: str = ""
    patient_id: int


class AccessCodeResetResponse(BaseModel):
    patient_id: int
    access_code: str


@router.post("/access-code", response_model=AccessCodeResetResponse)
async def reset_patient_access_code(
    body: AccessCodeResetRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Generate (or rotate) a patient's 6-digit portal access code.

    Intended for doctor-facing clients (mini-program, admin UI).  The
    plaintext code is returned once so the doctor can share it with the
    patient; only the PBKDF2 hash is stored in the database.

    Rotating the code also bumps ``access_code_version``, which
    invalidates all previously-issued patient portal JWTs.
    """
    from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback

    doctor_id = resolve_doctor_id_from_auth_or_fallback(
        (body.doctor_id or "").strip(),
        authorization,
        fallback_env_flag="PATIENT_PORTAL_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )

    enforce_doctor_rate_limit(doctor_id, scope="patient_portal.access_code", max_requests=10)

    from db.crud.patient import set_patient_access_code
    from utils.errors import PatientNotFoundError

    async with AsyncSessionLocal() as db:
        try:
            plaintext = await set_patient_access_code(db, doctor_id, body.patient_id)
        except PatientNotFoundError:
            raise HTTPException(status_code=404, detail="Patient not found")

    return AccessCodeResetResponse(patient_id=body.patient_id, access_code=plaintext)


async def _notify_doctor_safe(doctor_id: str, message: str) -> None:
    """Send notification to doctor, swallowing exceptions to avoid breaking the response."""
    try:
        await send_doctor_notification(doctor_id, message)
    except Exception:
        logger.exception(
            "[PatientPortal] failed to notify doctor_id=%s", doctor_id,
        )
