"""GET endpoints for form_responses. Ownership-gated on doctor_id."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models.form_response import FormResponseDB

router = APIRouter()


async def _resolve(
    authorization: Optional[str],
    x_doctor_id: Optional[str],
) -> str:
    """Resolve the doctor id from auth. Reuses doctor_intake's resolver."""
    from channels.web.doctor_intake.shared import _resolve_doctor_id as _inner
    return await _inner(x_doctor_id or "", authorization)


@router.get("/api/form_responses/{response_id}")
async def get_form_response(
    response_id: int,
    authorization: Optional[str] = Header(default=None),
    x_doctor_id: Optional[str] = Header(default=None, alias="X-Doctor-Id"),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor = await _resolve(authorization, x_doctor_id)

    row = await db.get(FormResponseDB, response_id)
    if row is None:
        raise HTTPException(404, "form response not found")
    if row.doctor_id != resolved_doctor:
        raise HTTPException(403, "not authorized for this response")

    return {
        "id": row.id,
        "doctor_id": row.doctor_id,
        "patient_id": row.patient_id,
        "template_id": row.template_id,
        "session_id": row.session_id,
        "payload": row.payload,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/api/patients/{patient_id}/form_responses")
async def list_form_responses(
    patient_id: int,
    template_id: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    x_doctor_id: Optional[str] = Header(default=None, alias="X-Doctor-Id"),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor = await _resolve(authorization, x_doctor_id)

    q = select(FormResponseDB).where(
        FormResponseDB.patient_id == patient_id,
        FormResponseDB.doctor_id == resolved_doctor,
    )
    if template_id:
        q = q.where(FormResponseDB.template_id == template_id)
    q = q.order_by(FormResponseDB.created_at.desc())

    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "template_id": r.template_id,
            "payload": r.payload,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
