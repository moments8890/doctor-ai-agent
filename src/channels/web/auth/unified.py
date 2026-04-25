"""Unified auth API endpoints — single login/register for doctors and patients."""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from infra.auth.rate_limit import enforce_ip_rate_limit
from infra.auth.unified import (
    authenticate,
    forget_me,
    issue_token,
    login,
    login_with_role,
    register_doctor,
    register_patient,
    revoke_user_tokens,
)

# Per-IP soft cap on unauthenticated login attempts. Layered with the per-account
# lockout (LOGIN_FAIL_THRESHOLD) so distributed brute force can't sidestep the
# account ceiling by spreading guesses across many nicknames from one IP.
_LOGIN_IP_RATE_PER_MIN = int(os.environ.get("LOGIN_IP_RATE_PER_MIN", "30"))

router = APIRouter(prefix="/api/auth", tags=["auth-unified"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    nickname: str
    passcode: str
    role: Optional[str] = None  # "doctor" or "patient" — set from the login tab so
                                # same nickname can coexist across roles without
                                # forcing a role picker every login.


class LoginWithRoleRequest(BaseModel):
    nickname: str
    passcode: str
    role: str  # "doctor" or "patient"
    doctor_id: Optional[str] = None
    patient_id: Optional[int] = None


class DoctorRegisterRequest(BaseModel):
    nickname: str
    passcode: str
    invite_code: str
    specialty: Optional[str] = None


class PatientRegisterRequest(BaseModel):
    nickname: str
    passcode: str
    doctor_id: str
    gender: Optional[str] = None


class QRTokenRequest(BaseModel):
    role: str  # "doctor" or "patient"
    doctor_id: Optional[str] = None  # optional — derived from JWT if not provided
    patient_id: Optional[int] = None


class QRTokenResponse(BaseModel):
    token: str
    url: str
    expires_in_days: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/unified/login")
async def unified_login(body: LoginRequest, request: Request):
    """Login with nickname + passcode, optionally constrained by role."""
    enforce_ip_rate_limit(
        request, scope="auth.unified.login",
        max_requests=_LOGIN_IP_RATE_PER_MIN,
    )
    return await login(body.nickname, body.passcode, role=body.role)


@router.post("/unified/login-role")
async def unified_login_with_role(body: LoginWithRoleRequest, request: Request):
    """Login with explicit role selection (after role picker)."""
    enforce_ip_rate_limit(
        request, scope="auth.unified.login",
        max_requests=_LOGIN_IP_RATE_PER_MIN,
    )
    return await login_with_role(
        body.nickname, body.passcode, body.role,
        doctor_id=body.doctor_id, patient_id=body.patient_id,
    )


class ForgetMeRequest(BaseModel):
    passcode: str  # current passcode, re-confirmation gate


@router.post("/unified/forget-me")
async def unified_forget_me(
    body: ForgetMeRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Right-to-be-forgotten — hard-delete the caller's account.

    Requires the current passcode (so a stolen token alone cannot trigger
    deletion). FK CASCADEs handle dependent rows; the audit_log keeps its
    history with the doctor_id pointer set to NULL.
    """
    payload = await authenticate(authorization)
    return await forget_me(
        role=payload.get("role"),
        doctor_id=payload.get("doctor_id"),
        patient_id=payload.get("patient_id"),
        passcode=body.passcode,
    )


@router.post("/unified/logout")
async def unified_logout(authorization: Optional[str] = Header(default=None)):
    """Bump the caller's passcode_version, invalidating every token they hold.

    Useful as "log out everywhere". Standard single-device logout can keep
    using client-side localStorage clear; this is the kill switch.
    """
    payload = await authenticate(authorization)
    await revoke_user_tokens(
        role=payload.get("role"),
        doctor_id=payload.get("doctor_id"),
        patient_id=payload.get("patient_id"),
    )
    return {"ok": True}


@router.post("/unified/register/doctor")
async def unified_register_doctor(body: DoctorRegisterRequest):
    """Register as doctor with invitation code."""
    result = await register_doctor(
        body.nickname, body.passcode, body.invite_code, body.specialty,
    )
    # Auto-preseed demo data so the doctor sees populated content on first visit.
    try:
        from db.engine import AsyncSessionLocal
        from channels.web.doctor_dashboard.preseed_service import seed_demo_data
        async with AsyncSessionLocal() as db:
            seed_result = await seed_demo_data(db, result["doctor_id"])
            if not seed_result.already_seeded:
                await db.commit()
    except Exception:
        pass  # non-blocking — registration succeeds even if preseed fails
    return result


@router.post("/unified/register/patient")
async def unified_register_patient(body: PatientRegisterRequest):
    """Register as patient under a doctor."""
    return await register_patient(
        body.nickname, body.passcode, body.doctor_id, body.gender,
    )


@router.get("/unified/me")
async def unified_me(authorization: Optional[str] = Header(default=None)):
    """Return current user info from token."""
    payload = await authenticate(authorization)
    return {
        "role": payload.get("role"),
        "doctor_id": payload.get("doctor_id"),
        "patient_id": payload.get("patient_id"),
        "name": payload.get("name"),
    }


@router.get("/unified/doctors")
async def list_doctors_for_registration(db: AsyncSession = Depends(get_db)):
    """List doctors accepting patients (for patient registration)."""
    from db.models import Doctor
    from sqlalchemy import select

    # accepting_patients column removed — all doctors are considered accepting
    rows = (await db.execute(
        select(Doctor).where(
            ~Doctor.doctor_id.like("inttest_%"),
        )
    )).scalars().all()

    return [
        {"doctor_id": d.doctor_id, "name": d.name or d.doctor_id, "department": d.department or ""}
        for d in rows
    ]


@router.post("/qr-token", response_model=QRTokenResponse)
async def generate_qr_token(
    body: QRTokenRequest,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Generate a long-lived token and URL for QR code sharing."""
    from db.models import Doctor
    from db.models.patient import Patient
    from sqlalchemy import select

    # --- Auth: use the same dev-fallback pattern as other doctor endpoints ---
    from infra.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
    doctor_id = resolve_doctor_id_from_auth_or_fallback(
        body.doctor_id, authorization,
        fallback_env_flag="QR_TOKEN",
    )

    if body.role not in ("doctor", "patient"):
        raise HTTPException(400, "role must be 'doctor' or 'patient'")

    # Validate doctor exists
    doctor = (await db.execute(
        select(Doctor).where(Doctor.doctor_id == doctor_id)
    )).scalar_one_or_none()
    if doctor is None:
        raise HTTPException(404, "Doctor not found")

    patient_name: Optional[str] = None

    if body.role == "patient":
        if body.patient_id is None:
            raise HTTPException(400, "patient_id required for patient role")
        patient = (await db.execute(
            select(Patient).where(
                Patient.id == body.patient_id,
                Patient.doctor_id == doctor_id,
            )
        )).scalar_one_or_none()
        if patient is None:
            raise HTTPException(404, "Patient not found or does not belong to this doctor")
        patient_name = patient.name

    # --- Issue 30-day token, stamped with the user's CURRENT pcv ---
    # Critical: if the doctor or patient has rotated their passcode (pcv > 1),
    # the QR token must carry that pcv too. Otherwise the token is born
    # invalid (authenticate() rejects it as revoked) the moment it's used.
    if body.role == "patient":
        token_pcv = (patient.passcode_version if patient is not None else 1) or 1
    else:
        token_pcv = (doctor.passcode_version or 1) if doctor is not None else 1

    ttl = 30 * 24 * 3600
    token = issue_token(
        role=body.role,
        doctor_id=doctor_id,
        patient_id=body.patient_id,
        name=patient_name or (doctor.name if body.role == "doctor" else None),
        ttl_seconds=ttl,
        passcode_version=token_pcv,
    )

    # --- Build URL ---
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:5173")
    if body.role == "patient":
        path = "/patient"
        params = urlencode({"token": token})
    else:
        path = "/doctor"
        params = urlencode({"token": token})
    url = f"{base_url}{path}?{params}"

    return QRTokenResponse(token=token, url=url, expires_in_days=30)
