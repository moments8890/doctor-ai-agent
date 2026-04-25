"""
Patient portal registration routes: access-code management + doctor listing.

The legacy POST /register and POST /login (phone + year_of_birth as auth)
were removed once the unified /api/auth/unified/* path replaced them with
hashed-passcode auth, lockout, and IP rate limiting. See the comment near
the bottom of this file for the rationale.

This module owns an APIRouter that is included into the main patient_portal
router (which already carries ``prefix="/api/patient"``), so routes here
use bare paths (e.g. ``/access-code``, not ``/api/patient/access-code``).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from infra.auth.rate_limit import enforce_doctor_rate_limit

logger = logging.getLogger(__name__)

registration_router = APIRouter(tags=["patient-portal"])


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
    db: AsyncSession = Depends(get_db),
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

    try:
        plaintext = await set_patient_access_code(db, doctor_id, body.patient_id)
    except PatientNotFoundError:
        raise HTTPException(status_code=404, detail="Patient not found")

    return AccessCodeResetResponse(patient_id=body.patient_id, access_code=plaintext)


# ---------------------------------------------------------------------------
# Patient self-registration & login-by-phone (ADR 0016)
# ---------------------------------------------------------------------------


@registration_router.get("/doctors")
async def list_accepting_doctors(db: AsyncSession = Depends(get_db)):
    """List doctors accepting patients (for patient registration)."""
    from db.models import Doctor

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


# Removed: POST /register and POST /login (phone + year_of_birth as auth).
# Both endpoints had no callers (verified across frontend + backend) and
# carried two real risks: (1) login without doctor_id matched the first
# Patient row across the whole table by phone+yob, an IDOR risk; and
# (2) neither had any rate limit or lockout. The unified
# /api/auth/unified/* path replaces them with hashed-passcode auth,
# per-account lockout, and IP rate limiting.
#
# /access-code above (doctor-issued patient portal pin) is the path that
# still mints PatientAuth credentials going forward.
