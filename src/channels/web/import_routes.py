"""Medical record import endpoint — upload image/PDF/scan for Vision LLM extraction."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from typing import Optional

from utils.log import log

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/medical-record", status_code=201)
async def import_medical_record_endpoint(
    file: UploadFile = File(...),
    patient_id: Optional[int] = Form(None),
    doctor_id: str = Form("web_doctor"),
):
    """Import image/PDF → OCR → extract fields → create interview session for doctor review."""
    file_bytes = await file.read()

    try:
        from domain.records.vision_import import import_to_interview

        result = await import_to_interview(
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
            doctor_id=doctor_id,
            patient_id=patient_id,
        )
        return JSONResponse(result, status_code=201)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("413:"):
            raise HTTPException(status_code=413, detail=msg[4:])
        if msg.startswith("415:"):
            raise HTTPException(status_code=415, detail=msg[4:])
        raise HTTPException(status_code=422, detail=msg[4:] if ":" in msg else msg)
    except RuntimeError as exc:
        log(f"[ImportAPI] Vision LLM error: {exc}")
        raise HTTPException(status_code=502, detail="Vision LLM 不可用")
