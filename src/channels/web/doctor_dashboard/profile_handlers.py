"""
Doctor profile routes: get and update doctor display name and specialty.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import Doctor
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Models ────────────────────────────────────────────────────────────────────

class DoctorProfileUpdate(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    clinic_name: Optional[str] = None
    bio: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/manage/profile", include_in_schema=True)
async def get_doctor_profile(
    doctor_id: str = Query(...),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return the doctor's display name, specialty, and onboarding status."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)
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
    db: AsyncSession = Depends(get_db),
):
    """Update the doctor's display name and specialty."""
    resolved_id = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await db.execute(select(Doctor).where(Doctor.doctor_id == resolved_id))
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")
        doctor.name = name
    if body.specialty is not None:
        doctor.specialty = body.specialty.strip() or None
    if body.clinic_name is not None:
        doctor.clinic_name = body.clinic_name.strip() or None
    if body.bio is not None:
        doctor.bio = body.bio.strip() or None

    await db.commit()

    return {"ok": True, "name": doctor.name or "", "specialty": doctor.specialty or "", "clinic_name": getattr(doctor, "clinic_name", "") or "", "bio": getattr(doctor, "bio", "") or ""}
