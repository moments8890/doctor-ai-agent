"""
Patient portal registration routes: access-code management, doctor listing,
patient self-registration, and phone-based login.

This module owns an APIRouter that is included into the main patient_portal
router (which already carries ``prefix="/api/patient"``), so routes here
use bare paths (e.g. ``/register``, not ``/api/patient/register``).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Patient
from db.models.patient_auth import PatientAuth
from infra.auth.rate_limit import enforce_doctor_rate_limit

from infra.auth import UserRole
from infra.auth.unified import issue_token as _issue_unified_token

logger = logging.getLogger(__name__)

registration_router = APIRouter(tags=["patient-portal"])


async def _get_access_code_version(db, patient_id: int) -> int:
    """Fetch access_code_version from PatientAuth for JWT generation."""
    auth_row = (
        await db.execute(
            select(PatientAuth).where(PatientAuth.patient_id == patient_id).limit(1)
        )
    ).scalar_one_or_none()
    return auth_row.access_code_version if auth_row is not None else 0


# ---------------------------------------------------------------------------
# Access-code management (doctor-facing)
# ---------------------------------------------------------------------------

class AccessCodeResetRequest(BaseModel):
    doctor_id: str = ""
    patient_id: int


class AccessCodeResetResponse(BaseModel):
    patient_id: int
    access_code: str


@registration_router.post("/access-code", response_model=AccessCodeResetResponse)
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


# ---------------------------------------------------------------------------
# Patient self-registration & login-by-phone (ADR 0016)
# ---------------------------------------------------------------------------


@registration_router.get("/doctors")
async def list_accepting_doctors():
    """List doctors accepting patients (for patient registration)."""
    from db.models import Doctor

    async with AsyncSessionLocal() as db:
        # accepting_patients column removed — all doctors are considered accepting
        stmt = select(Doctor).where(
            ~Doctor.doctor_id.like("inttest_%"),
        )
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


@registration_router.post("/register")
async def register_patient(body: PatientRegisterRequest):
    """Patient self-registration. Links to existing record if name matches."""
    from db.models import Doctor

    doctor_id = body.doctor_id
    name = body.name
    gender = body.gender
    year_of_birth = body.year_of_birth
    phone = body.phone

    if not doctor_id or not name or not phone or not year_of_birth:
        raise HTTPException(400, "\u8bf7\u586b\u5199\u5b8c\u6574\u4fe1\u606f")

    async with AsyncSessionLocal() as db:
        # Validate doctor exists and is accepting
        doctor = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == doctor_id)
        )).scalar_one_or_none()
        if doctor is None:
            raise HTTPException(404, "\u672a\u627e\u5230\u8be5\u533b\u751f")

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
                raise HTTPException(400, "\u4fe1\u606f\u4e0e\u5df2\u6709\u8bb0\u5f55\u4e0d\u7b26\uff0c\u8bf7\u8054\u7cfb\u533b\u751f\u786e\u8ba4")
            if patient.year_of_birth and patient.year_of_birth != year_of_birth:
                raise HTTPException(400, "\u4fe1\u606f\u4e0e\u5df2\u6709\u8bb0\u5f55\u4e0d\u7b26\uff0c\u8bf7\u8054\u7cfb\u533b\u751f\u786e\u8ba4")
            if patient.phone and patient.phone != phone:
                raise HTTPException(400, "\u4fe1\u606f\u4e0e\u5df2\u6709\u8bb0\u5f55\u4e0d\u7b26\uff0c\u8bf7\u8054\u7cfb\u533b\u751f\u786e\u8ba4")
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

    token = _issue_unified_token(UserRole.patient, doctor_id, patient.id, patient.name)
    return {"token": token, "patient_id": patient.id, "patient_name": patient.name}


class PatientLoginRequest(BaseModel):
    phone: str
    year_of_birth: int
    doctor_id: Optional[str] = None


@registration_router.post("/login")
async def login_by_phone(body: PatientLoginRequest):
    """Patient login with phone + year_of_birth."""
    phone = body.phone
    year_of_birth = body.year_of_birth
    doctor_id = body.doctor_id

    if not phone or not year_of_birth:
        raise HTTPException(400, "\u8bf7\u8f93\u5165\u624b\u673a\u53f7\u548c\u51fa\u751f\u5e74\u4efd")

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
                raise HTTPException(401, "\u624b\u673a\u53f7\u6216\u51fa\u751f\u5e74\u4efd\u4e0d\u6b63\u786e")
            token = _issue_unified_token(UserRole.patient, doctor_id, patient.id, patient.name)
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
                raise HTTPException(401, "\u624b\u673a\u53f7\u6216\u51fa\u751f\u5e74\u4efd\u4e0d\u6b63\u786e")
            if len(patients) == 1:
                p = patients[0]
                token = _issue_unified_token(UserRole.patient, p.doctor_id, p.id, p.name)
                return {"token": token, "patient_id": p.id, "patient_name": p.name, "doctor_id": p.doctor_id}
            # Multiple doctors -- return list for picker
            return {
                "needs_doctor_selection": True,
                "doctors": [
                    {"doctor_id": p.doctor_id, "patient_name": p.name}
                    for p in patients
                ],
            }
