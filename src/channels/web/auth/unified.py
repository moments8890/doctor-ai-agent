"""Unified auth API endpoints — single login/register for doctors and patients."""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from infra.auth.unified import (
    authenticate,
    issue_token,
    login,
    login_with_role,
    register_doctor,
    register_patient,
)

router = APIRouter(prefix="/api/auth", tags=["auth-unified"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    phone: str
    year_of_birth: int


class LoginWithRoleRequest(BaseModel):
    phone: str
    year_of_birth: int
    role: str  # "doctor" or "patient"
    doctor_id: Optional[str] = None
    patient_id: Optional[int] = None


class DoctorRegisterRequest(BaseModel):
    phone: str
    name: str
    year_of_birth: int
    invite_code: str
    specialty: Optional[str] = None


class PatientRegisterRequest(BaseModel):
    phone: str
    name: str
    year_of_birth: int
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
async def unified_login(body: LoginRequest):
    """Login with phone + year_of_birth. Auto-detects role."""
    return await login(body.phone, body.year_of_birth)


@router.post("/unified/login-role")
async def unified_login_with_role(body: LoginWithRoleRequest):
    """Login with explicit role selection (after role picker)."""
    return await login_with_role(
        body.phone, body.year_of_birth, body.role,
        doctor_id=doctor_id, patient_id=body.patient_id,
    )


@router.post("/unified/register/doctor")
async def unified_register_doctor(body: DoctorRegisterRequest):
    """Register as doctor with invitation code."""
    return await register_doctor(
        body.phone, body.name, body.year_of_birth,
        body.invite_code, body.specialty,
    )


@router.post("/unified/register/patient")
async def unified_register_patient(body: PatientRegisterRequest):
    """Register as patient under a doctor."""
    return await register_patient(
        body.phone, body.name, body.year_of_birth,
        body.doctor_id, body.gender,
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

    # --- Issue 30-day token ---
    ttl = 30 * 24 * 3600
    token = issue_token(
        role=body.role,
        doctor_id=doctor_id,
        patient_id=body.patient_id,
        name=patient_name or (doctor.name if body.role == "doctor" else None),
        ttl_seconds=ttl,
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
