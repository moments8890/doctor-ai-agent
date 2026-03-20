"""Review queue endpoints: list, detail, confirm, update field."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from sqlalchemy import select
from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB
from db.crud.review import (
    list_reviews,
    get_review_detail,
    confirm_review,
    update_review_field,
)
from domain.records.schema import FIELD_KEYS
from infra.observability.audit import audit
from infra.auth.rate_limit import enforce_doctor_rate_limit
from channels.web.ui._utils import _resolve_ui_doctor_id
from utils.log import safe_create_task, log

router = APIRouter(tags=["ui"], include_in_schema=False)


class FieldUpdate(BaseModel):
    field: str
    value: str


@router.get("/api/manage/review-queue", include_in_schema=True)
async def list_review_queue(
    doctor_id: str = Query(default="web_doctor"),
    status: str = Query(default="pending_review"),
    limit: int = Query(default=50, le=200),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.review.list")
    async with AsyncSessionLocal() as db:
        items = await list_reviews(db, resolved, status=status, limit=limit)
    return {"items": items, "count": len(items)}


@router.get("/api/manage/review-queue/{queue_id}", include_in_schema=True)
async def get_review_detail_endpoint(
    queue_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.review.detail")
    async with AsyncSessionLocal() as db:
        detail = await get_review_detail(db, queue_id, resolved)
    if detail is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return detail


@router.post("/api/manage/review-queue/{queue_id}/confirm", include_in_schema=True)
async def confirm_review_endpoint(
    queue_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.review.confirm")
    async with AsyncSessionLocal() as db:
        rq = await confirm_review(db, queue_id, resolved)
        if rq is None:
            raise HTTPException(status_code=404, detail="Review not found or already confirmed")
        await db.commit()
    safe_create_task(audit(resolved, "review.confirmed", "review", str(rq.record_id)))
    # Best-effort: create case_history entry
    try:
        import json as _json
        from db.crud.case_history import create_case as _create_case
        async with AsyncSessionLocal() as db2:
            _rec = (await db2.execute(
                select(MedicalRecordDB).where(MedicalRecordDB.id == rq.record_id)
            )).scalar_one_or_none()
            if _rec and _rec.structured:
                _s = _json.loads(_rec.structured)
                _cc = _s.get("chief_complaint", "")
                if _cc:
                    await _create_case(
                        db2, doctor_id=resolved, record_id=rq.record_id,
                        patient_id=rq.patient_id,
                        chief_complaint=_cc,
                        present_illness=_s.get("present_illness", ""),
                    )
                    await db2.commit()
    except Exception as _e:
        log(f"[review] case_history creation failed (non-blocking): {_e}", level="warning")
    return {"id": rq.id, "status": rq.status, "reviewed_at": rq.reviewed_at.isoformat() if rq.reviewed_at else None}


@router.patch("/api/manage/review-queue/{queue_id}/record", include_in_schema=True)
async def update_review_field_endpoint(
    queue_id: int,
    body: FieldUpdate,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.review.edit")
    if body.field not in FIELD_KEYS:
        raise HTTPException(status_code=422, detail=f"Unknown field: {body.field}")
    async with AsyncSessionLocal() as db:
        result = await update_review_field(db, queue_id, resolved, body.field, body.value)
        if result is None:
            raise HTTPException(status_code=404, detail="Review or record not found")
        await db.commit()
    safe_create_task(audit(resolved, "review.field_edited", "review", str(result["record_id"])))
    return result
