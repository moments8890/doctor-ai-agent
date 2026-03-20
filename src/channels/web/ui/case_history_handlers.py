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
