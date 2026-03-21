"""Case history enrichment endpoint: promote preliminary → confirmed."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from db.engine import AsyncSessionLocal
from db.crud.case_history import confirm_case
from infra.observability.audit import audit
from infra.auth.rate_limit import enforce_doctor_rate_limit
from channels.web.ui._utils import _resolve_ui_doctor_id, _fmt_ts
from utils.log import safe_create_task

router = APIRouter(tags=["ui"], include_in_schema=False)


class CaseEnrichment(BaseModel):
    final_diagnosis: str
    treatment: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    key_symptoms: Optional[List[str]] = None


@router.get("/api/manage/case-history")
async def list_cases_endpoint(
    doctor_id: str = Query(default="web_doctor"),
    status: str = Query(default="confirmed"),
    authorization: Optional[str] = Header(default=None),
):
    """List cases for a doctor, filtered by status."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    from db.crud.case_history import list_cases
    async with AsyncSessionLocal() as session:
        cases = await list_cases(session, resolved, status=status)
    return {
        "cases": [
            {
                "id": c.id,
                "chief_complaint": c.chief_complaint,
                "final_diagnosis": c.final_diagnosis,
                "treatment": c.treatment,
                "outcome": c.outcome,
                "reference_count": getattr(c, "reference_count", 0) or 0,
                "confidence_status": c.confidence_status,
                "created_at": _fmt_ts(c.created_at),
            }
            for c in cases
        ]
    }


@router.get("/api/manage/case-history/{case_id}")
async def get_case_detail_endpoint(
    case_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Get a single case by id."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    from db.crud.case_history import get_case_by_id
    async with AsyncSessionLocal() as session:
        case = await get_case_by_id(session, resolved, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="未找到病例")
    return {
        "id": case.id,
        "chief_complaint": case.chief_complaint,
        "present_illness": case.present_illness,
        "final_diagnosis": case.final_diagnosis,
        "treatment": case.treatment,
        "outcome": case.outcome,
        "notes": case.notes,
        "key_symptoms": case.key_symptoms,
        "reference_count": getattr(case, "reference_count", 0) or 0,
        "confidence_status": case.confidence_status,
        "source": case.source,
        "embedding_model": case.embedding_model,
        "created_at": _fmt_ts(case.created_at),
        "updated_at": _fmt_ts(case.updated_at),
    }


@router.patch("/api/manage/case-history/{case_id}", include_in_schema=True)
async def enrich_case_endpoint(
    case_id: int,
    body: CaseEnrichment,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Enrich a preliminary case with final diagnosis and treatment."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.case_history.enrich")
    async with AsyncSessionLocal() as db:
        case = await confirm_case(
            db, case_id, resolved,
            final_diagnosis=body.final_diagnosis,
            treatment=body.treatment,
            outcome=body.outcome,
            notes=body.notes,
            key_symptoms=body.key_symptoms,
        )
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        await db.commit()
    safe_create_task(audit(resolved, "case_history.confirmed", "case_history", str(case_id)))
    return {
        "id": case.id,
        "status": case.confidence_status,
        "created_at": _fmt_ts(case.created_at),
        "updated_at": _fmt_ts(case.updated_at),
    }
