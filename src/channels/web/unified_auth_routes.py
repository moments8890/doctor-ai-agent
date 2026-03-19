"""Unified auth API endpoints — single login/register for doctors and patients."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from infra.auth.unified import (
    authenticate,
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
        doctor_id=body.doctor_id, patient_id=body.patient_id,
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
async def list_doctors_for_registration():
    """List doctors accepting patients (for patient registration)."""
    from db.engine import AsyncSessionLocal
    from db.models import Doctor
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Doctor).where(Doctor.accepting_patients == True)
        )).scalars().all()

    return [
        {"doctor_id": d.doctor_id, "name": d.name or d.doctor_id, "department": d.department or ""}
        for d in rows
    ]
