"""Unified authentication for doctors and patients.

Single JWT system with role-based access. Both roles log in with phone + year_of_birth.
Doctors require an invitation code at sign-up (one-time).
"""
from __future__ import annotations

import os
import time
from typing import Optional

import jwt
from fastapi import Header, HTTPException

from infra.auth import UserRole
from utils.log import log

_TOKEN_TTL = int(os.environ.get("UNIFIED_TOKEN_TTL", "604800"))  # 7 days default
_AUDIENCE = "doctor-ai-agent"


def _secret() -> str:
    secret = os.environ.get("UNIFIED_AUTH_SECRET", "")
    if not secret:
        env = os.environ.get("ENVIRONMENT", "").strip().lower()
        if env not in ("development", "dev", "test", ""):
            raise RuntimeError("UNIFIED_AUTH_SECRET must be set in production.")
        secret = "dev-unified-secret-change-me"
    return secret


def issue_token(
    role: str,
    doctor_id: Optional[str] = None,
    patient_id: Optional[int] = None,
    name: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
) -> str:
    """Issue a unified JWT token."""
    now = int(time.time())
    payload = {
        "role": role,  # "doctor" or "patient"
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "name": name,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + (ttl_seconds if ttl_seconds is not None else _TOKEN_TTL),
    }
    # Set sub based on role
    if role == UserRole.doctor:
        payload["sub"] = doctor_id
    else:
        payload["sub"] = str(patient_id)
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_token(token: str) -> dict:
    """Verify JWT and return payload. Raises HTTPException on failure."""
    if not token:
        raise HTTPException(401, "Missing token")
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"], audience=_AUDIENCE)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    return payload


def extract_token(authorization: Optional[str] = None) -> str:
    """Extract Bearer token from Authorization header."""
    if not authorization:
        raise HTTPException(401, "Authorization header required")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return authorization


async def authenticate(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Authenticate from Authorization header. Returns JWT payload."""
    token = extract_token(authorization)
    return verify_token(token)


async def require_doctor(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Authenticate and require doctor role."""
    payload = await authenticate(authorization)
    if payload.get("role") != UserRole.doctor:
        raise HTTPException(403, "Doctor access required")
    return payload


async def require_patient(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Authenticate and require patient role."""
    payload = await authenticate(authorization)
    if payload.get("role") != UserRole.patient:
        raise HTTPException(403, "Patient access required")
    return payload


async def login(phone: str, year_of_birth: int) -> dict:
    """Login with phone + YOB. Detects role automatically.

    Returns:
        - Single match: {token, role, doctor_id, patient_id, name}
        - Multiple matches: {needs_role_selection: True, roles: [...]}
        - No match: raises 401
    """
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select

    results = []

    async with AsyncSessionLocal() as db:
        # Check doctors
        doctor = (await db.execute(
            select(Doctor).where(
                Doctor.phone == phone,
                Doctor.year_of_birth == year_of_birth,
            )
        )).scalar_one_or_none()

        if doctor:
            results.append({
                "role": UserRole.doctor,
                "doctor_id": doctor.doctor_id,
                "patient_id": None,
                "name": doctor.name or doctor.doctor_id,
            })

        # Check patients (may have multiple under different doctors)
        patients = (await db.execute(
            select(Patient).where(
                Patient.phone == phone,
                Patient.year_of_birth == year_of_birth,
            )
        )).scalars().all()

        for p in patients:
            results.append({
                "role": UserRole.patient,
                "doctor_id": p.doctor_id,
                "patient_id": p.id,
                "name": p.name,
            })

    if not results:
        raise HTTPException(401, "手机号或出生年份不正确")

    if len(results) == 1:
        r = results[0]
        token = issue_token(r["role"], r["doctor_id"], r["patient_id"], r["name"])
        return {"token": token, **r}

    # Multiple matches — return list for role picker
    return {
        "needs_role_selection": True,
        "roles": results,
    }


async def login_with_role(phone: str, year_of_birth: int, role: str, doctor_id: Optional[str] = None, patient_id: Optional[int] = None) -> dict:
    """Login with explicit role selection (after role picker)."""
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        if role == UserRole.doctor:
            doctor = (await db.execute(
                select(Doctor).where(
                    Doctor.phone == phone,
                    Doctor.year_of_birth == year_of_birth,
                )
            )).scalar_one_or_none()
            if not doctor:
                raise HTTPException(401, "登录失败")
            token = issue_token(UserRole.doctor, doctor.doctor_id, None, doctor.name)
            return {"token": token, "role": UserRole.doctor, "doctor_id": doctor.doctor_id, "name": doctor.name}

        elif role == UserRole.patient:
            stmt = select(Patient).where(
                Patient.phone == phone,
                Patient.year_of_birth == year_of_birth,
            )
            if patient_id:
                stmt = stmt.where(Patient.id == patient_id)
            elif doctor_id:
                stmt = stmt.where(Patient.doctor_id == doctor_id)
            patient = (await db.execute(stmt)).scalars().first()
            if not patient:
                raise HTTPException(401, "登录失败")
            token = issue_token(UserRole.patient, patient.doctor_id, patient.id, patient.name)
            return {"token": token, "role": UserRole.patient, "doctor_id": patient.doctor_id, "patient_id": patient.id, "name": patient.name}

    raise HTTPException(400, "Invalid role")


async def register_doctor(phone: str, name: str, year_of_birth: int, invite_code: str, specialty: Optional[str] = None) -> dict:
    """Register a new doctor with invitation code."""
    from db.engine import AsyncSessionLocal
    from db.models import Doctor
    from db.models.doctor import InviteCode
    from sqlalchemy import select
    import secrets

    async with AsyncSessionLocal() as db:
        # Validate invite code
        code_row = (await db.execute(
            select(InviteCode).where(InviteCode.code == invite_code)
        )).scalar_one_or_none()

        if code_row is None or not code_row.active:
            raise HTTPException(400, "邀请码无效")
        if code_row.expires_at and code_row.expires_at < __import__("datetime").datetime.utcnow():
            raise HTTPException(400, "邀请码已过期")
        if code_row.max_uses > 0 and code_row.used_count >= code_row.max_uses:
            raise HTTPException(400, "邀请码已被使用")

        # Check if phone already registered as doctor
        existing = (await db.execute(
            select(Doctor).where(Doctor.phone == phone)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(400, "该手机号已注册为医生")

        # Create doctor
        doctor_id = f"inv_{secrets.token_urlsafe(9)}"
        doctor = Doctor(
            doctor_id=doctor_id,
            name=name,
            phone=phone,
            year_of_birth=year_of_birth,
            specialty=specialty,
        )
        db.add(doctor)

        # Mark invite code as used
        code_row.used_count += 1
        if not code_row.doctor_id:
            code_row.doctor_id = doctor_id

        await db.commit()

    log(f"[auth] doctor registered id={doctor_id} name={name} phone={phone}")
    token = issue_token(UserRole.doctor, doctor_id, None, name)
    return {"token": token, "role": UserRole.doctor, "doctor_id": doctor_id, "name": name}


async def register_patient(phone: str, name: str, year_of_birth: int, doctor_id: str, gender: Optional[str] = None) -> dict:
    """Register a new patient under a doctor."""
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Validate doctor exists and accepts patients
        doctor = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == doctor_id)
        )).scalar_one_or_none()
        if doctor is None:
            raise HTTPException(404, "未找到该医生")

        # Check for existing patient (link or conflict)
        patient = (await db.execute(
            select(Patient).where(Patient.doctor_id == doctor_id, Patient.name == name)
        )).scalar_one_or_none()

        if patient:
            # Validate non-null fields
            if patient.gender and gender and patient.gender != gender:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            if patient.year_of_birth and patient.year_of_birth != year_of_birth:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            if patient.phone and patient.phone != phone:
                raise HTTPException(400, "信息与已有记录不符，请联系医生确认")
            # Backfill
            if not patient.gender and gender:
                patient.gender = gender
            if not patient.year_of_birth:
                patient.year_of_birth = year_of_birth
            if not patient.phone:
                patient.phone = phone
            await db.commit()
        else:
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

    log(f"[auth] patient registered id={patient.id} name={name} doctor={doctor_id}")
    token = issue_token(UserRole.patient, doctor_id, patient.id, name)
    return {"token": token, "role": UserRole.patient, "doctor_id": doctor_id, "patient_id": patient.id, "name": name}
