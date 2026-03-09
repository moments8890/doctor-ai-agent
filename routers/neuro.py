"""
神经专科路由：提供神经科病例的结构化录入和查询 API 端点。
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from db.crud import get_neuro_cases_for_doctor, save_neuro_case
from db.engine import AsyncSessionLocal
from services.ai.neuro_structuring import extract_neuro_case
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
from utils.log import log

router = APIRouter(prefix="/api/neuro", tags=["neuro"])


class NeuroFromTextInput(BaseModel):
    text: str
    doctor_id: str = "test_doctor"


class NeuroCaseSummary(BaseModel):
    id: int
    patient_name: Optional[str] = None
    nihss: Optional[int] = None
    created_at: str


@router.post("/from-text")
async def neuro_from_text(
    body: NeuroFromTextInput,
    authorization: Optional[str] = Header(default=None),
):
    """Extract a structured neurovascular case from free text.

    Returns the full NeuroCase, ExtractionLog, and the saved DB row id.
    """
    doctor_id = resolve_doctor_id_from_auth_or_fallback(
        body.doctor_id,
        authorization,
        fallback_env_flag="NEURO_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(doctor_id, scope="neuro.from_text")
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")
    try:
        neuro_case, extraction_log, _cvd_ctx = await extract_neuro_case(body.text)
    except ValueError as exc:
        log(f"[Neuro] extract validation FAILED doctor={doctor_id}: {exc}")
        raise HTTPException(status_code=422, detail="Invalid neuro case content")
    except Exception as exc:
        log(f"[Neuro] extract FAILED doctor={doctor_id}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")

    async with AsyncSessionLocal() as db:
        row = await save_neuro_case(db, doctor_id, neuro_case, extraction_log)

    return {
        "case": neuro_case.model_dump(),
        "log": extraction_log.model_dump(),
        "db_id": row.id,
    }


@router.get("/cases", response_model=List[NeuroCaseSummary])
async def list_neuro_cases(
    doctor_id: Optional[str] = None,
    limit: int = 20,
    authorization: Optional[str] = Header(default=None),
):
    """Return recent neurovascular cases for a doctor."""
    resolved_doctor_id = resolve_doctor_id_from_auth_or_fallback(
        doctor_id,
        authorization,
        fallback_env_flag="NEURO_ALLOW_BODY_DOCTOR_ID",
        default_doctor_id="test_doctor",
    )
    enforce_doctor_rate_limit(resolved_doctor_id, scope="neuro.list_cases")
    async with AsyncSessionLocal() as db:
        rows = await get_neuro_cases_for_doctor(db, resolved_doctor_id, limit=limit)

    return [
        NeuroCaseSummary(
            id=r.id,
            patient_name=r.neuro_patient_name,
            nihss=r.nihss,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
