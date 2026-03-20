"""Diagnosis endpoints: get results, update item decisions, confirm."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud.diagnosis import get_diagnosis_by_record, update_item_decision, confirm_diagnosis
from infra.observability.audit import audit
from infra.auth.rate_limit import enforce_doctor_rate_limit
from channels.web.ui._utils import _resolve_ui_doctor_id
from utils.log import safe_create_task

router = APIRouter(tags=["ui"], include_in_schema=False)


class ItemDecisionBody(BaseModel):
    type: str       # "differentials" | "workup" | "treatment"
    index: int
    decision: str   # "confirmed" | "rejected"


@router.get("/api/manage/diagnosis/{record_id}", include_in_schema=True)
async def get_diagnosis_endpoint(
    record_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.diagnosis.get")
    async with AsyncSessionLocal() as db:
        diag = await get_diagnosis_by_record(db, record_id, resolved)
    if diag is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found")
    return {
        "id": diag.id,
        "record_id": diag.record_id,
        "status": diag.status,
        "ai_output": json.loads(diag.ai_output) if diag.ai_output else None,
        "doctor_decisions": json.loads(diag.doctor_decisions) if diag.doctor_decisions else {},
        "red_flags": json.loads(diag.red_flags) if diag.red_flags else [],
        "case_references": json.loads(diag.case_references) if diag.case_references else [],
        "agreement_score": diag.agreement_score,
        "error_message": diag.error_message,
        "created_at": diag.created_at.isoformat() if diag.created_at else None,
        "completed_at": diag.completed_at.isoformat() if diag.completed_at else None,
        "confirmed_at": diag.confirmed_at.isoformat() if diag.confirmed_at else None,
    }


@router.patch("/api/manage/diagnosis/{diagnosis_id}/decide", include_in_schema=True)
async def decide_item_endpoint(
    diagnosis_id: int,
    body: ItemDecisionBody,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.diagnosis.decide")
    if body.type not in ("differentials", "workup", "treatment"):
        raise HTTPException(status_code=422, detail=f"Invalid type: {body.type}")
    if body.decision not in ("confirmed", "rejected"):
        raise HTTPException(status_code=422, detail=f"Invalid decision: {body.decision}")
    async with AsyncSessionLocal() as db:
        diag = await update_item_decision(db, diagnosis_id, resolved, body.type, body.index, body.decision)
        if diag is None:
            raise HTTPException(status_code=404, detail="Diagnosis not found")
        await db.commit()
    safe_create_task(audit(resolved, "diagnosis.item_decided", "diagnosis", str(diagnosis_id)))
    return {"id": diag.id, "status": "updated"}


@router.post("/api/manage/diagnosis/{diagnosis_id}/confirm", include_in_schema=True)
async def confirm_diagnosis_endpoint(
    diagnosis_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.diagnosis.confirm")
    async with AsyncSessionLocal() as db:
        diag = await confirm_diagnosis(db, diagnosis_id, resolved)
        if diag is None:
            raise HTTPException(status_code=404, detail="Diagnosis not found or already confirmed")
        await db.commit()
    safe_create_task(audit(resolved, "diagnosis.confirmed", "diagnosis", str(diagnosis_id)))
    return {"id": diag.id, "status": diag.status, "agreement_score": diag.agreement_score}
