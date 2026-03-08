"""
病历导出路由：生成患者病历 PDF，供医生下载或通过微信发送。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB, MedicalRecordExport, Patient
from routers.ui._utils import _resolve_ui_doctor_id
from services.export.pdf_export import generate_outpatient_report_pdf, generate_records_pdf
from services.observability.audit import audit
from utils.log import log


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

router = APIRouter(prefix="/api/export", tags=["export"])

# ---------------------------------------------------------------------------
# Filename helpers (no PHI in filenames)
# ---------------------------------------------------------------------------

_SAFE_FILENAME_RE = re.compile(r"[^\w\u4e00-\u9fff\-]")


def _safe_pdf_filename(prefix: str, patient_id: int, suffix: str = "") -> str:
    """Return an opaque filename that does not contain patient name (PHI)."""
    safe_suffix = _SAFE_FILENAME_RE.sub("_", suffix)[:20] if suffix else ""
    parts = [prefix, str(patient_id)]
    if safe_suffix:
        parts.append(safe_suffix)
    return "_".join(parts) + ".pdf"


# ---------------------------------------------------------------------------
# Magic-byte MIME validation (server-side, not trusting Content-Type header)
# ---------------------------------------------------------------------------

# Each entry: (magic_bytes_prefix, set_of_allowed_declared_mime_types)
_MAGIC_SIGNATURES: list[tuple[bytes, set[str]]] = [
    (b"%PDF", {"application/pdf"}),
    (b"PK\x03\x04", {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }),
    (b"\xff\xd8\xff", {"image/jpeg"}),
    (b"\x89PNG\r\n\x1a\n", {"image/png"}),
    # WEBP: RIFF????WEBP
    (b"RIFF", {"image/webp"}),
]


def _validate_magic_bytes(raw: bytes, declared_mime: str) -> None:
    """Raise HTTPException 415 if file magic bytes do not match declared MIME."""
    for magic, allowed_mimes in _MAGIC_SIGNATURES:
        if raw[:len(magic)] == magic:
            # Special-case WEBP: bytes 8-12 must be b"WEBP"
            if magic == b"RIFF" and raw[8:12] != b"WEBP":
                continue
            if declared_mime not in allowed_mimes:
                raise HTTPException(
                    status_code=415,
                    detail=f"File magic bytes indicate a different type than declared '{declared_mime}'",
                )
            return  # matched and validated
    # No magic signature matched; for text/plain this is fine
    if declared_mime != "text/plain":
        log(f"[Export] warning: no magic signature match for declared mime={declared_mime}")


# ---------------------------------------------------------------------------
# Patient PDF export
# ---------------------------------------------------------------------------

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "image/jpeg",
    "image/png",
    "image/webp",
}
_MAX_TEMPLATE_BYTES = 1 * 1024 * 1024  # 1 MB (was 10 MB — only 500 chars used in prompt)


@router.get("/patient/{patient_id}/pdf")
async def export_patient_pdf(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    """
    Export all medical records for a patient as a PDF file.
    Returns: application/pdf with Content-Disposition: attachment.
    Filename uses patient_id only (no PHI in filename).
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        patient_result = await db.execute(
            select(Patient).where(Patient.id == patient_id, Patient.doctor_id == resolved_doctor_id)
        )
        patient = patient_result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail="Patient not found")

        records_result = await db.execute(
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == resolved_doctor_id,
            )
            .order_by(MedicalRecordDB.created_at.asc())
            .limit(limit)
        )
        records = list(records_result.scalars().all())

    # Audit: log the export action
    asyncio.create_task(audit(resolved_doctor_id, "EXPORT", resource_type="patient", resource_id=str(patient_id)))

    try:
        pdf_bytes = generate_records_pdf(
            records=records,
            patient=patient,
            patient_name=patient.name,
        )
    except Exception as exc:
        log(f"[Export] PDF generation failed for patient {patient_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF generation failed")

    # Write export audit rows for each record
    pdf_hash = _sha256_hex(pdf_bytes)
    async def _write_export_audit():
        async with AsyncSessionLocal() as db:
            for rec in records:
                db.add(MedicalRecordExport(
                    record_id=rec.id,
                    doctor_id=resolved_doctor_id,
                    export_format="pdf",
                    exported_at=datetime.now(timezone.utc),
                    pdf_hash=pdf_hash,
                ))
            await db.commit()
    asyncio.create_task(_write_export_audit())

    filename = _safe_pdf_filename("病历", patient_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/record/{record_id}/pdf")
async def export_record_pdf(
    record_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    """
    Export a single medical record as a PDF file.
    Filename uses record_id only (no PHI in filename).
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        record_result = await db.execute(
            select(MedicalRecordDB).where(
                MedicalRecordDB.id == record_id,
                MedicalRecordDB.doctor_id == resolved_doctor_id,
            )
        )
        record = record_result.scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=404, detail="Record not found")

        patient_name = None
        if record.patient_id is not None:
            patient_result = await db.execute(
                select(Patient).where(Patient.id == record.patient_id)
            )
            p = patient_result.scalar_one_or_none()
            if p:
                patient_name = p.name

    asyncio.create_task(audit(resolved_doctor_id, "EXPORT", resource_type="record", resource_id=str(record_id)))

    try:
        pdf_bytes = generate_records_pdf(
            records=[record],
            patient_name=patient_name,
        )
    except Exception as exc:
        log(f"[Export] PDF generation failed for record {record_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF generation failed")

    # Write export audit row
    pdf_hash = _sha256_hex(pdf_bytes)
    async def _write_record_export_audit():
        async with AsyncSessionLocal() as db:
            db.add(MedicalRecordExport(
                record_id=record_id,
                doctor_id=resolved_doctor_id,
                export_format="pdf",
                exported_at=datetime.now(timezone.utc),
                pdf_hash=pdf_hash,
            ))
            await db.commit()
    asyncio.create_task(_write_record_export_audit())

    filename = _safe_pdf_filename("病历_record", record_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


# ---------------------------------------------------------------------------
# China Standard Outpatient Report
# ---------------------------------------------------------------------------

@router.get("/patient/{patient_id}/outpatient-report")
async def export_outpatient_report(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    """
    Generate a 卫生部 2010 门诊病历 format PDF for a patient.
    LLM extracts structured fields from all records; custom template (if any) is used.
    Filename uses patient_id only (no PHI).
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        patient_result = await db.execute(
            select(Patient).where(Patient.id == patient_id, Patient.doctor_id == resolved_doctor_id)
        )
        patient = patient_result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=404, detail="Patient not found")

        records_result = await db.execute(
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == resolved_doctor_id,
            )
            .order_by(MedicalRecordDB.created_at.asc())
            .limit(limit)
        )
        records = list(records_result.scalars().all())

    if not records:
        raise HTTPException(status_code=404, detail="No records found for this patient")

    asyncio.create_task(
        audit(resolved_doctor_id, "EXPORT", resource_type="outpatient_report", resource_id=str(patient_id))
    )

    from services.export.outpatient_report import ExtractionError, extract_outpatient_fields

    try:
        fields = await extract_outpatient_fields(records, patient, doctor_id=resolved_doctor_id)
    except ExtractionError as exc:
        log(f"[Export] outpatient field extraction unavailable for patient {patient_id}: {exc}")
        raise HTTPException(
            status_code=502,
            detail="LLM service unavailable for field extraction. Please retry.",
        )

    # Build patient info line (age calculated properly)
    parts: list[str] = []
    if getattr(patient, "gender", None):
        parts.append(patient.gender)
    if getattr(patient, "year_of_birth", None):
        from datetime import date
        age = date.today().year - int(patient.year_of_birth)
        parts.append(f"{age}岁")
    patient_info = "  ".join(parts) if parts else None

    try:
        pdf_bytes = generate_outpatient_report_pdf(
            fields=fields,
            patient_name=patient.name,
            patient_info=patient_info,
        )
    except Exception as exc:
        log(f"[Export] outpatient report PDF render failed for patient {patient_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF generation failed")

    filename = _safe_pdf_filename("门诊病历", patient_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


# ---------------------------------------------------------------------------
# Custom report template upload / management
# ---------------------------------------------------------------------------

@router.post("/template/upload")
async def upload_report_template(
    file: UploadFile = File(...),
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    """
    Upload a custom report template (PDF / Word / image / text).
    The template text is extracted and stored in system_prompts under
    key  report.template.{doctor_id}.  Future outpatient reports for
    this doctor will use it as a format reference (first 500 chars only).
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)

    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Allowed: PDF, Word, image, text.",
        )

    raw = await file.read()
    if len(raw) > _MAX_TEMPLATE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 1 MB)")

    # Server-side magic byte validation (not just trusting Content-Type header)
    _validate_magic_bytes(raw, content_type)

    # Extract text from the uploaded file
    text = await _extract_template_text(raw, content_type)
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from the uploaded file")

    # Persist to system_prompts (key scoped to doctor, never raw interpolation with user input)
    key = f"report.template.{resolved_doctor_id}"
    from db.crud import upsert_system_prompt
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, text)

    safe_filename = os.path.basename(file.filename or "unknown")
    log(f"[Export] template uploaded doctor={resolved_doctor_id} file={safe_filename!r} chars={len(text)}")
    asyncio.create_task(
        audit(resolved_doctor_id, "WRITE", resource_type="report_template", resource_id=resolved_doctor_id)
    )
    return JSONResponse({"status": "ok", "chars": len(text)})


@router.get("/template/status")
async def get_template_status(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    """Return whether a custom template exists for this doctor."""
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    key = f"report.template.{resolved_doctor_id}"
    from db.crud import get_system_prompt
    async with AsyncSessionLocal() as db:
        row = await get_system_prompt(db, key)
    if row and row.content:
        return {"has_template": True, "chars": len(row.content)}
    return {"has_template": False, "chars": 0}


@router.delete("/template")
async def delete_report_template(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    """Delete the custom template for this doctor (revert to default format)."""
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    key = f"report.template.{resolved_doctor_id}"
    from db.crud import upsert_system_prompt
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, "")
    asyncio.create_task(
        audit(resolved_doctor_id, "DELETE", resource_type="report_template", resource_id=resolved_doctor_id)
    )
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Template text extraction helpers
# ---------------------------------------------------------------------------

async def _extract_template_text(raw: bytes, content_type: str) -> str:
    """Extract plain text from PDF, Word, image, or text files."""
    if content_type == "text/plain":
        import chardet
        enc = chardet.detect(raw).get("encoding") or "utf-8"
        return raw.decode(enc, errors="replace")

    if content_type == "application/pdf":
        return _extract_pdf_text(raw)

    if content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return _extract_docx_text(raw)

    if content_type.startswith("image/"):
        return await _extract_image_text(raw, content_type)

    return ""


def _extract_pdf_text(raw: bytes) -> str:
    """Extract text from PDF bytes using pypdf (if installed) or pdfminer."""
    try:
        import io
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass
    except Exception as exc:
        log(f"[Export] pypdf extraction failed: {exc}")
    try:
        import io
        from pdfminer.high_level import extract_text as pm_extract  # type: ignore
        return pm_extract(io.BytesIO(raw))
    except ImportError:
        pass
    except Exception as exc:
        log(f"[Export] pdfminer extraction failed: {exc}")
    return raw.decode("utf-8", errors="replace")


def _extract_docx_text(raw: bytes) -> str:
    """Extract text from Word .docx bytes."""
    try:
        import io
        from docx import Document  # type: ignore
        doc = Document(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception as exc:
        log(f"[Export] docx extraction failed: {exc}")
        return ""


async def _extract_image_text(raw: bytes, content_type: str) -> str:
    """OCR image using the shared vision LLM service (singleton client, with fallback)."""
    try:
        from services.ai.vision import extract_text_from_image
        text = await extract_text_from_image(raw, content_type)
        if not text.strip():
            raise HTTPException(status_code=422, detail="Vision model returned empty text for this image")
        return text
    except HTTPException:
        raise
    except Exception as exc:
        log(f"[Export] image OCR failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Image text extraction failed (vision LLM error). Please upload a text or PDF file instead.",
        )
