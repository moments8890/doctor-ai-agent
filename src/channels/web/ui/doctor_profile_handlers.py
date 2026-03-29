"""
Doctor profile routes: get and update doctor display name and specialty.
"""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from db.crud.patient import create_patient, find_patient_by_name
from db.engine import AsyncSessionLocal
from db.models import Doctor
from channels.web.ui._utils import _resolve_ui_doctor_id
from infra.auth import UserRole
from infra.auth.unified import issue_token

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Models ────────────────────────────────────────────────────────────────────

class DoctorProfileUpdate(BaseModel):
    name: str
    specialty: Optional[str] = None
    clinic_name: Optional[str] = None
    bio: Optional[str] = None


class OnboardingPatientEntryRequest(BaseModel):
    doctor_id: str
    patient_name: str
    gender: Optional[str] = None
    age: Optional[int] = None


class OnboardingPatientEntryResponse(BaseModel):
    status: str
    patient_id: int
    patient_name: str
    created: bool
    portal_token: str
    portal_url: str
    expires_in_days: int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/manage/profile", include_in_schema=True)
async def get_doctor_profile(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Return the doctor's display name, specialty, and onboarding status."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Doctor).where(Doctor.doctor_id == resolved_id))
        doctor = result.scalar_one_or_none()

    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")

    name = doctor.name or ""
    specialty = getattr(doctor, "specialty", None) or ""
    clinic_name = getattr(doctor, "clinic_name", None) or ""
    bio = getattr(doctor, "bio", None) or ""
    onboarded = bool(name and name != resolved_id)
    return {
        "doctor_id": resolved_id,
        "name": name,
        "specialty": specialty,
        "clinic_name": clinic_name,
        "bio": bio,
        "onboarded": onboarded,
    }


@router.patch("/api/manage/profile", include_in_schema=True)
async def patch_doctor_profile(
    body: DoctorProfileUpdate,
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
):
    """Update the doctor's display name and specialty."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Doctor).where(Doctor.doctor_id == resolved_id))
        doctor = result.scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status_code=404, detail="Doctor not found")
        doctor.name = name
        try:
            doctor.specialty = body.specialty or None
        except Exception:
            pass  # specialty column not yet migrated — skip
        try:
            doctor.clinic_name = body.clinic_name or None
            doctor.bio = body.bio or None
        except Exception:
            pass  # columns not yet migrated — skip
        await db.commit()

    return {"ok": True, "name": name, "specialty": body.specialty or "", "clinic_name": body.clinic_name or "", "bio": body.bio or ""}


@router.post(
    "/api/manage/onboarding/patient-entry",
    response_model=OnboardingPatientEntryResponse,
    include_in_schema=True,
)
async def create_onboarding_patient_entry(
    body: OnboardingPatientEntryRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Create or reuse a patient, then return a deterministic patient-entry URL."""
    resolved_doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    patient_name = (body.patient_name or "").strip()
    if not patient_name:
        raise HTTPException(status_code=422, detail="patient_name is required")
    if len(patient_name) > 128:
        raise HTTPException(status_code=422, detail="patient_name too long")

    async with AsyncSessionLocal() as db:
        patient = await find_patient_by_name(db, resolved_doctor_id, patient_name)
        created = False
        if patient is None:
            patient, _plaintext_code = await create_patient(
                db,
                resolved_doctor_id,
                patient_name,
                body.gender,
                body.age,
            )
            created = True

    ttl_days = 30
    ttl_seconds = ttl_days * 24 * 3600
    portal_token = issue_token(
        role=UserRole.patient,
        doctor_id=resolved_doctor_id,
        patient_id=patient.id,
        name=patient.name,
        ttl_seconds=ttl_seconds,
    )
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:5173")
    portal_url = f"{base_url}/patient?{urlencode({'token': portal_token})}"

    return OnboardingPatientEntryResponse(
        status="ok",
        patient_id=patient.id,
        patient_name=patient.name,
        created=created,
        portal_token=portal_token,
        portal_url=portal_url,
        expires_in_days=ttl_days,
    )
