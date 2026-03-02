from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.crud import get_neuro_cases_for_doctor, save_neuro_case
from db.engine import AsyncSessionLocal
from services.neuro_structuring import extract_neuro_case

router = APIRouter(prefix="/api/neuro", tags=["neuro"])


class NeuroFromTextInput(BaseModel):
    text: str
    doctor_id: str = "test_doctor"


class NeuroCaseSummary(BaseModel):
    id: int
    patient_name: Optional[str] = None
    chief_complaint: Optional[str] = None
    primary_diagnosis: Optional[str] = None
    nihss: Optional[int] = None
    created_at: str


@router.post("/from-text")
async def neuro_from_text(body: NeuroFromTextInput):
    """Extract a structured neurovascular case from free text.

    Returns the full NeuroCase, ExtractionLog, and the saved DB row id.
    """
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="Text input cannot be empty.")
    try:
        neuro_case, extraction_log = await extract_neuro_case(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    async with AsyncSessionLocal() as db:
        row = await save_neuro_case(db, body.doctor_id, neuro_case, extraction_log)

    return {
        "case": neuro_case.model_dump(),
        "log": extraction_log.model_dump(),
        "db_id": row.id,
    }


@router.get("/cases", response_model=List[NeuroCaseSummary])
async def list_neuro_cases(doctor_id: str, limit: int = 20):
    """Return recent neurovascular cases for a doctor."""
    async with AsyncSessionLocal() as db:
        rows = await get_neuro_cases_for_doctor(db, doctor_id, limit=limit)

    return [
        NeuroCaseSummary(
            id=r.id,
            patient_name=r.patient_name,
            chief_complaint=r.chief_complaint,
            primary_diagnosis=r.primary_diagnosis,
            nihss=r.nihss,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
