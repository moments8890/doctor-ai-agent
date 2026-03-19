"""
患者自助门户 API：患者可查看自己的病历并向医生发送消息。

认证流程：
  患者输入姓名 + 医生 doctor_id + 6 位 access_code → 精确匹配 Patient 表
  → 校验 PBKDF2-SHA256 哈希 → 签发短期 JWT（含 access_code_version）。
  旧患者（access_code 为 NULL）允许仅姓名登录，并在日志中记录 deprecation 警告。
"""

from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from typing import Optional

import jwt
from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Patient, MedicalRecordDB
from db.crud.patient_message import save_patient_message
from infra.auth.access_code_hash import hash_access_code, verify_access_code
from infra.auth.rate_limit import enforce_doctor_rate_limit
from domain.tasks.notifications import send_doctor_notification
from infra.observability.audit import audit
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
        from infra.auth import is_production
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


async def _authenticate_patient(
    x_patient_token: Optional[str] = None,
    authorization: Optional[str] = None,
) -> Patient:
    """Validate patient token from either X-Patient-Token or Authorization: Bearer.

    Supports both legacy patient portal tokens and unified auth tokens.
    Returns the Patient ORM instance on success; raises HTTPException otherwise.
    """
    # Try unified Bearer token first
    bearer = authorization
    if bearer and bearer.startswith("Bearer "):
        bearer = bearer[7:]
    if bearer:
        try:
            from infra.auth.unified import verify_token
            payload = verify_token(bearer)
            if payload.get("role") != "patient":
                raise HTTPException(403, "Patient access required")
            patient_id = payload.get("patient_id")
            token_doctor_id = payload.get("doctor_id")

            async with AsyncSessionLocal() as db:
                stmt = select(Patient).where(Patient.id == patient_id)
                if token_doctor_id:
                    stmt = stmt.where(Patient.doctor_id == token_doctor_id)
                patient = (await db.execute(stmt.limit(1))).scalar_one_or_none()

            if patient is None:
                raise HTTPException(404, "Patient not found")
            return patient
        except HTTPException:
            raise
        except Exception:
            pass  # Fall through to legacy token

    # Legacy X-Patient-Token
    if not x_patient_token:
        raise HTTPException(status_code=401, detail="Authentication required")
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
    from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback

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


# ---------------------------------------------------------------------------
# Patient self-registration & login-by-phone (ADR 0016)
# ---------------------------------------------------------------------------


@router.get("/doctors")
async def list_accepting_doctors():
    """List doctors accepting patients (for patient registration)."""
    from db.models import Doctor

    async with AsyncSessionLocal() as db:
        stmt = select(Doctor).where(Doctor.accepting_patients == True)
        rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "doctor_id": d.doctor_id,
            "name": d.name or d.doctor_id,
            "department": d.department or "",
        }
        for d in rows
    ]


class PatientRegisterRequest(BaseModel):
    doctor_id: str
    name: str
    gender: Optional[str] = None
    year_of_birth: int
    phone: str


@router.post("/register")
async def register_patient(body: PatientRegisterRequest):
    """Patient self-registration. Links to existing record if name matches."""
    from db.models import Doctor

    doctor_id = body.doctor_id
    name = body.name
    gender = body.gender
    year_of_birth = body.year_of_birth
    phone = body.phone

    if not doctor_id or not name or not phone or not year_of_birth:
        raise HTTPException(400, "请填写完整信息")

    async with AsyncSessionLocal() as db:
        # Validate doctor exists and is accepting
        doctor = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == doctor_id)
        )).scalar_one_or_none()
        if doctor is None or not doctor.accepting_patients:
            raise HTTPException(404, "未找到该医生")

        # Check for existing patient record
        patient = (await db.execute(
            select(Patient).where(
                Patient.doctor_id == doctor_id,
                Patient.name == name,
            )
        )).scalar_one_or_none()

        if patient:
            # Validate non-null fields don't conflict
            if patient.gender and gender and patient.gender != gender:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            if patient.year_of_birth and patient.year_of_birth != year_of_birth:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            if patient.phone and patient.phone != phone:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            # Backfill nulls
            if not patient.gender and gender:
                patient.gender = gender
            if not patient.year_of_birth:
                patient.year_of_birth = year_of_birth
            if not patient.phone:
                patient.phone = phone
            await db.commit()
        else:
            # Create new patient
            patient = Patient(
                doctor_id=doctor_id,
                name=name,
                gender=gender,
                year_of_birth=year_of_birth,
                phone=phone,
            )
            db.add(patient)
            await db.commit()
            await db.refresh(patient)

    token = _issue_patient_token(patient.id, doctor_id, getattr(patient, "access_code_version", 0))
    return {"token": token, "patient_id": patient.id, "patient_name": patient.name}


class PatientLoginRequest(BaseModel):
    phone: str
    year_of_birth: int
    doctor_id: Optional[str] = None


@router.post("/login")
async def login_by_phone(body: PatientLoginRequest):
    """Patient login with phone + year_of_birth."""
    phone = body.phone
    year_of_birth = body.year_of_birth
    doctor_id = body.doctor_id

    if not phone or not year_of_birth:
        raise HTTPException(400, "请输入手机号和出生年份")

    async with AsyncSessionLocal() as db:
        if doctor_id:
            # Direct login to specific doctor
            patient = (await db.execute(
                select(Patient).where(
                    Patient.doctor_id == doctor_id,
                    Patient.phone == phone,
                    Patient.year_of_birth == year_of_birth,
                )
            )).scalar_one_or_none()
            if patient is None:
                raise HTTPException(401, "手机号或出生年份不正确")
            token = _issue_patient_token(patient.id, doctor_id, getattr(patient, "access_code_version", 0))
            return {"token": token, "patient_id": patient.id, "patient_name": patient.name, "doctor_id": doctor_id}
        else:
            # Find all patient records for this phone+yob
            patients = (await db.execute(
                select(Patient).where(
                    Patient.phone == phone,
                    Patient.year_of_birth == year_of_birth,
                )
            )).scalars().all()
            if not patients:
                raise HTTPException(401, "手机号或出生年份不正确")
            if len(patients) == 1:
                p = patients[0]
                token = _issue_patient_token(p.id, p.doctor_id, getattr(p, "access_code_version", 0))
                return {"token": token, "patient_id": p.id, "patient_name": p.name, "doctor_id": p.doctor_id}
            # Multiple doctors — return list for picker
            return {
                "needs_doctor_selection": True,
                "doctors": [
                    {"doctor_id": p.doctor_id, "patient_name": p.name}
                    for p in patients
                ],
            }


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
        log(f"[PatientUpload] Vision LLM error: {exc}")
        raise HTTPException(status_code=502, detail="文件识别失败，请稍后重试")
