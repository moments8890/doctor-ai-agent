"""
Single-patient PDF export endpoints: per-patient PDF, per-record PDF, outpatient report.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .shared import (
    _content_disposition,
    _safe_pdf_filename,
    _sha256_hex,
)
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models import MedicalRecordDB, Patient
from domain.records.pdf_export import VALID_SECTIONS, generate_outpatient_report_pdf, generate_records_pdf
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.audit import audit
from utils.log import log, safe_create_task

patient_router = APIRouter()

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VISIT_RANGE_MAP = {"5": 5, "10": 10, "all": 9999}


async def _fetch_patient_and_records(
    db,
    patient_id: int,
    resolved_doctor_id: str,
    limit: int,
):
    """Fetch patient row and associated records; raises 404 if patient not found."""
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
    return patient, list(records_result.scalars().all())


def _write_patient_export_audit_task(records, resolved_doctor_id: str, pdf_hash: str) -> None:
    """No-op — MedicalRecordExport table removed."""
    pass


def _write_outpatient_export_audit_task(
    records, resolved_doctor_id: str,
    export_fmt: str = "pdf", pdf_hash: Optional[str] = None,
) -> None:
    """No-op — MedicalRecordExport table removed."""
    pass


async def _fetch_record_and_patient(db, record_id: int, resolved_doctor_id: str):
    """Fetch a single medical record and its patient; raises 404 if not found."""
    record_result = await db.execute(
        select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == resolved_doctor_id,
        )
    )
    record = record_result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    patient = None
    if record.patient_id is not None:
        patient_result = await db.execute(
            select(Patient).where(
                Patient.id == record.patient_id,
                Patient.doctor_id == resolved_doctor_id,
            )
        )
        patient = patient_result.scalar_one_or_none()
    return record, patient


def _build_patient_info_line(patient) -> Optional[str]:
    """Build a concise '男  45岁' info line for the outpatient report header."""
    from utils.response_formatting import build_patient_info_line
    return build_patient_info_line(patient)


async def _extract_outpatient_fields_safe(
    records, patient, resolved_doctor_id: str, patient_id: int,
):
    """Call LLM field extraction; raises HTTPException 502 on ExtractionError."""
    from domain.records.outpatient_report import ExtractionError, extract_outpatient_fields
    try:
        return await extract_outpatient_fields(
            records, patient, doctor_id=resolved_doctor_id,
        )
    except ExtractionError as exc:
        log(f"[Export] outpatient field extraction unavailable for patient {patient_id}: {exc}")
        raise HTTPException(
            status_code=502,
            detail="LLM service unavailable for field extraction. Please retry.",
        )


def _source_annotation(records: list) -> Optional[str]:
    """Build a '综合 … 至 … 共 N 条记录' annotation when multiple records are merged."""
    if len(records) <= 1:
        return None
    dates = [r.created_at for r in records if getattr(r, "created_at", None)]
    if not dates:
        return None
    return (
        f"综合 {min(dates).strftime('%Y-%m-%d')} 至 "
        f"{max(dates).strftime('%Y-%m-%d')} 共 {len(records)} 条记录"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@patient_router.get("/patient/{patient_id}/pdf")
async def export_patient_pdf(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    sections: Optional[str] = Query(default=None),
    visit_range: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Export medical records for a patient as a PDF file.

    Optional filters:
    - **sections**: comma-separated section keys to include
      (``basic,diagnosis,visits,prescriptions,allergies``).
      Omit to export all sections (default).
    - **visit_range**: ``5``, ``10``, or ``all``.  Overrides *limit* when
      provided.

    Returns: application/pdf with Content-Disposition: attachment.
    Filename uses patient_id only (no PHI in filename).
    """
    # --- Validate sections ---------------------------------------------------
    parsed_sections: Optional[set] = None
    if sections:
        parsed_sections = {s.strip() for s in sections.split(",") if s.strip()}
        unknown = parsed_sections - VALID_SECTIONS
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown section(s): {', '.join(sorted(unknown))}. "
                       f"Valid sections: {', '.join(sorted(VALID_SECTIONS))}",
            )

    # --- Validate & apply visit_range ----------------------------------------
    if visit_range is not None:
        if visit_range not in _VISIT_RANGE_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid visit_range '{visit_range}'. Must be one of: 5, 10, all",
            )
        limit = _VISIT_RANGE_MAP[visit_range]

    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor_id, scope="export.patient_pdf")
    patient, records = await _fetch_patient_and_records(db, patient_id, resolved_doctor_id, limit)
    try:
        pdf_bytes = generate_records_pdf(
            records=records,
            patient=patient,
            patient_name=patient.name,
            sections=parsed_sections,
        )
    except Exception as exc:
        log(f"[Export] PDF generation failed for patient {patient_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    # Audit after successful generation — not before, so failed exports
    # don't leave a misleading EXPORT entry in the audit trail.
    safe_create_task(audit(resolved_doctor_id, "EXPORT", resource_type="patient", resource_id=str(patient_id)))
    pdf_hash = _sha256_hex(pdf_bytes)
    _write_patient_export_audit_task(records, resolved_doctor_id, pdf_hash)
    filename = _safe_pdf_filename("病历", patient_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@patient_router.get("/record/{record_id}/pdf")
async def export_record_pdf(
    record_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Export a single medical record as a PDF file.
    Filename uses record_id only (no PHI in filename).
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor_id, scope="export.record_pdf")
    record, patient = await _fetch_record_and_patient(db, record_id, resolved_doctor_id)
    patient_name = patient.name if patient else None
    try:
        pdf_bytes = generate_records_pdf(
            records=[record], patient_name=patient_name,
            patient=patient,
        )
    except Exception as exc:
        log(f"[Export] PDF generation failed for record {record_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_create_task(audit(resolved_doctor_id, "EXPORT", resource_type="record", resource_id=str(record_id)))
    filename = _safe_pdf_filename("病历_record", record_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@patient_router.get("/patient/{patient_id}/outpatient-report")
async def export_outpatient_report(
    patient_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    export_format: str = Query(default="pdf", alias="format", pattern="^(json|pdf)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a 卫生部 2010 门诊病历 format report for a patient.

    Use ``?format=json`` to receive structured JSON instead of PDF.
    LLM extracts structured fields from all records; custom template (if any) is used.
    Filename uses patient_id only (no PHI).
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved_doctor_id, scope="export.outpatient_report")
    patient, records = await _fetch_patient_and_records(db, patient_id, resolved_doctor_id, limit)
    if not records:
        raise HTTPException(status_code=404, detail="No records found for this patient")

    # --- JSON export path --------------------------------------------------
    if export_format == "json":
        from domain.records.outpatient_report import export_as_json
        data = await export_as_json(records, patient, resolved_doctor_id)
        annotation = _source_annotation(records)
        if annotation:
            data["source_annotation"] = annotation
        safe_create_task(
            audit(resolved_doctor_id, "EXPORT", resource_type="outpatient_report", resource_id=str(patient_id))
        )
        # Audit row with export_format="json"
        _write_outpatient_export_audit_task(records, resolved_doctor_id, export_fmt="json")
        return JSONResponse(data)

    # --- PDF export path (default) -----------------------------------------
    fields = await _extract_outpatient_fields_safe(
        records, patient, resolved_doctor_id, patient_id,
    )
    patient_info_str = _build_patient_info_line(patient)
    patient_info_data: dict = {"text": patient_info_str}
    annotation = _source_annotation(records)
    if annotation:
        patient_info_data["source_annotation"] = annotation
    try:
        pdf_bytes = generate_outpatient_report_pdf(
            fields=fields,
            patient_name=patient.name,
            patient_info=patient_info_data,
        )
    except Exception as exc:
        log(f"[Export] outpatient report PDF render failed for patient {patient_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    safe_create_task(
        audit(resolved_doctor_id, "EXPORT", resource_type="outpatient_report", resource_id=str(patient_id))
    )
    pdf_hash = _sha256_hex(pdf_bytes)
    _write_outpatient_export_audit_task(records, resolved_doctor_id, export_fmt="pdf", pdf_hash=pdf_hash)
    filename = _safe_pdf_filename("门诊病历", patient_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )
