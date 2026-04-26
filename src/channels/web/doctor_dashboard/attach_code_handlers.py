"""Doctor-side endpoint for the permanent patient attach code.

Returns the doctor's `patient_attach_code` plus a deep-link URL that, when
encoded as a QR code, takes a patient straight to the registration form
with the code pre-filled.

The code is permanent — there is no rotation endpoint by design (beta
acceptance per design spec). The width of the column (VARCHAR(8)) leaves
room to grow from the v0 4-char default to 6 or 8 without a schema change.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import Doctor
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from infra.attach_code import generate_code

router = APIRouter(tags=["ui"], include_in_schema=False)

# Public URL where the patient registration page lives. Configurable per env.
_QR_LINK_BASE = os.environ.get("PATIENT_REGISTER_BASE_URL", "https://patient.doctoragentai.cn")


@router.get("/api/manage/patient-attach-code", include_in_schema=True)
async def get_patient_attach_code(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return the doctor's permanent attach code + the deep-link QR URL."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    doctor = (await db.execute(
        select(Doctor).where(Doctor.doctor_id == resolved)
    )).scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=404, detail="doctor not found")

    # Lazy backfill — covers any doctor row created after the migration ran
    # (e.g., a fresh signup before deploy reaches their shard). Retries on
    # the rare unique-constraint collision.
    if not doctor.patient_attach_code:
        for _ in range(50):
            doctor.patient_attach_code = generate_code()
            try:
                await db.commit()
                await db.refresh(doctor)
                break
            except IntegrityError:
                await db.rollback()
                doctor = (await db.execute(
                    select(Doctor).where(Doctor.doctor_id == resolved)
                )).scalar_one_or_none()
                if doctor is None:
                    raise HTTPException(status_code=404, detail="doctor not found")
                if doctor.patient_attach_code:
                    break

    code = doctor.patient_attach_code
    qr_url = f"{_QR_LINK_BASE}/patient/register?code={code}"
    return {"code": code, "qr_url": qr_url}
