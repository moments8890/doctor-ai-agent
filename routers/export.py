"""
病历导出路由：生成患者病历 PDF，供医生下载或通过微信发送。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB, Patient
from routers.ui._utils import _resolve_ui_doctor_id
from services.export.pdf_export import generate_records_pdf
from utils.log import log

router = APIRouter(prefix="/api/export", tags=["export"])


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
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)

    async with AsyncSessionLocal() as db:
        # Verify patient belongs to this doctor
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

    try:
        pdf_bytes = generate_records_pdf(
            records=records,
            patient_name=patient.name,
        )
    except Exception as exc:
        log(f"[Export] PDF generation failed for patient {patient_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF generation failed")

    safe_name = (patient.name or f"patient_{patient_id}").replace(" ", "_").replace("/", "_")
    filename = f"病历_{safe_name}.pdf"
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

    try:
        pdf_bytes = generate_records_pdf(
            records=[record],
            patient_name=patient_name,
        )
    except Exception as exc:
        log(f"[Export] PDF generation failed for record {record_id}: {exc}")
        raise HTTPException(status_code=500, detail="PDF generation failed")

    safe_name = (patient_name or f"record_{record_id}").replace(" ", "_").replace("/", "_")
    filename = f"病历_{safe_name}_{record_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
