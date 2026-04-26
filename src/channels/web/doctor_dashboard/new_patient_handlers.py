"""New-patient detection endpoints — count of unviewed patients in the last
24h + an idempotent mark-viewed sink the patient-detail page calls after a
short dwell on the doctor-app side.

These power three surfaces:
- MyAIPage 今日关注 row "新患者 N 位刚刚加入"
- Patient list per-row "新" badge
- (Optional) red dot on the 患者 tab in the bottom nav

Security model (Codex review):
- doctor_id always derived from auth (no client-trusted query param for
  security). The shared `_resolve_ui_doctor_id` helper handles the dev
  fallback consistently with the rest of the dashboard.
- Cross-doctor patient access returns 404 "Patient not found" (NOT 403),
  matching the pattern in patient_detail_handlers.py — never reveals that
  a patient ID exists under a different doctor.
- mark-viewed is idempotent: writes only when first_doctor_view_at IS NULL.
  First view wins; later views never overwrite.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models.patient import Patient
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id

router = APIRouter(tags=["ui"], include_in_schema=False)

# A patient is "new" only while BOTH conditions hold: not yet viewed by the
# doctor AND created within the last 24h. The time bound prevents a dropped
# mark-viewed POST from stranding the badge forever (Codex correctness fix).
_NEW_WINDOW = timedelta(hours=24)


@router.get("/api/manage/patients/unseen-count", include_in_schema=True)
async def unseen_patient_count(
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return how many of THIS doctor's patients are new+unviewed."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    cutoff = datetime.utcnow() - _NEW_WINDOW
    count = (await db.execute(
        select(func.count(Patient.id)).where(
            Patient.doctor_id == resolved,
            Patient.first_doctor_view_at.is_(None),
            Patient.created_at >= cutoff,
        )
    )).scalar_one()
    return {"count": int(count or 0)}


@router.post(
    "/api/manage/patients/{patient_id}/mark-viewed",
    include_in_schema=True,
)
async def mark_patient_viewed(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent: stamps `first_doctor_view_at = NOW()` only if currently
    NULL. The frontend fires this after the patient detail page has been
    foregrounded for ~2s (dwell threshold per Codex review).

    Cross-doctor access returns 404 to avoid revealing patient existence.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    patient = (await db.execute(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.doctor_id == resolved,
        )
    )).scalar_one_or_none()
    if patient is None:
        # Same envelope whether the patient doesn't exist or belongs to a
        # different doctor — never leak existence across the doctor boundary.
        raise HTTPException(status_code=404, detail="Patient not found")

    was_null = patient.first_doctor_view_at is None
    if was_null:
        # First view wins — never overwrite a prior timestamp.
        await db.execute(
            update(Patient)
            .where(
                Patient.id == patient_id,
                Patient.doctor_id == resolved,
                Patient.first_doctor_view_at.is_(None),
            )
            .values(first_doctor_view_at=datetime.utcnow())
        )
        await db.commit()
    return {"id": patient_id, "first_doctor_view_at_set": was_null}
