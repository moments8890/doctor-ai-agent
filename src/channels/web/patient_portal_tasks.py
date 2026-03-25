"""
Patient portal task & record-detail routes.

Provides:
  GET  /tasks                   — patient-visible tasks (target='patient')
  POST /tasks/{id}/complete     — mark a patient task as completed
  POST /upload-result           — confirm which task a file upload fulfils
  GET  /records/{id}            — single record with diagnosis + treatment plan
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from channels.web.patient_portal_auth import _authenticate_patient
from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB
from db.models.tasks import DoctorTask
from domain.tasks.notifications import send_doctor_notification
from infra.observability.audit import audit
from utils.log import safe_create_task

logger = logging.getLogger(__name__)

tasks_router = APIRouter(tags=["patient-portal"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PatientTaskOut(BaseModel):
    id: int
    task_type: str
    title: str
    content: Optional[str] = None
    status: str
    due_at: Optional[datetime] = None
    source_type: Optional[str] = None
    created_at: datetime


class PatientRecordDetailOut(BaseModel):
    id: int
    record_type: str
    content: Optional[str] = None
    structured: Optional[dict] = None
    status: Optional[str] = None
    created_at: datetime
    diagnosis_status: Optional[str] = None
    treatment_plan: Optional[Dict[str, Any]] = None


class UploadResultRequest(BaseModel):
    task_id: int
    record_id: int


class UploadResultResponse(BaseModel):
    ok: bool
    task_id: int
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@tasks_router.get("/tasks", response_model=list[PatientTaskOut])
async def get_patient_tasks(authorization: Optional[str] = Header(default=None)):
    """Return tasks targeted at this patient (target='patient')."""
    patient = await _authenticate_patient(authorization)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DoctorTask)
            .where(
                DoctorTask.target == "patient",
                DoctorTask.patient_id == patient.id,
            )
            .order_by(DoctorTask.created_at.desc())
            .limit(200)
        )
        tasks = result.scalars().all()

    safe_create_task(audit(
        "patient", "READ",
        resource_type="patient_tasks", resource_id=str(patient.id),
    ))
    return [
        PatientTaskOut(
            id=t.id,
            task_type=t.task_type,
            title=t.title,
            content=t.content,
            status=t.status,
            due_at=t.due_at,
            source_type=t.source_type,
            created_at=t.created_at,
        )
        for t in tasks
    ]


@tasks_router.post("/tasks/{task_id}/complete", response_model=PatientTaskOut)
async def complete_patient_task(
    task_id: int,
    authorization: Optional[str] = Header(default=None),
):
    """Mark a patient-targeted task as completed."""
    patient = await _authenticate_patient(authorization)

    async with AsyncSessionLocal() as db:
        task = (await db.execute(
            select(DoctorTask)
            .where(DoctorTask.id == task_id)
        )).scalar_one_or_none()

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.patient_id != patient.id or task.target != "patient":
            raise HTTPException(status_code=404, detail="Task not found")

        task.status = "completed"
        task.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(task)

    safe_create_task(audit(
        "patient", "UPDATE",
        resource_type="patient_task", resource_id=str(task_id),
    ))
    return PatientTaskOut(
        id=task.id,
        task_type=task.task_type,
        title=task.title,
        content=task.content,
        status=task.status,
        due_at=task.due_at,
        source_type=task.source_type,
        created_at=task.created_at,
    )


@tasks_router.post("/upload-result", response_model=UploadResultResponse)
async def confirm_upload_result(
    body: UploadResultRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Patient confirms which pending task their upload fulfils.

    Verifies task belongs to this patient and is pending, then marks it
    completed and notifies the doctor.
    """
    patient = await _authenticate_patient(authorization)

    async with AsyncSessionLocal() as db:
        task = (await db.execute(
            select(DoctorTask).where(DoctorTask.id == body.task_id)
        )).scalar_one_or_none()

        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.patient_id != patient.id or task.target != "patient":
            raise HTTPException(status_code=404, detail="Task not found")

        if task.status != "pending":
            raise HTTPException(
                status_code=409,
                detail="Task is not pending (current: {0})".format(task.status),
            )

        # Verify record belongs to this patient
        record = (await db.execute(
            select(MedicalRecordDB).where(
                MedicalRecordDB.id == body.record_id,
                MedicalRecordDB.patient_id == patient.id,
            )
        )).scalar_one_or_none()

        if record is None:
            raise HTTPException(status_code=404, detail="Record not found")

        task.status = "completed"
        task.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(task)

    logger.info(
        "[PatientPortal] upload-result confirmed | patient_id=%s task_id=%s record_id=%s",
        patient.id, body.task_id, body.record_id,
    )

    # Notify doctor (fire-and-forget)
    notification_text = "患者【{name}】上传了检查结果（{title}），请查看。".format(
        name=patient.name, title=task.title,
    )
    safe_create_task(_notify_doctor_safe(patient.doctor_id, notification_text))

    safe_create_task(audit(
        "patient", "UPDATE",
        resource_type="upload_result", resource_id=str(body.task_id),
    ))

    return UploadResultResponse(
        ok=True,
        task_id=task.id,
        status=task.status,
    )


async def _notify_doctor_safe(doctor_id: str, message: str) -> None:
    """Send notification to doctor, swallowing exceptions."""
    try:
        await send_doctor_notification(doctor_id, message)
    except Exception:
        logger.exception(
            "[PatientPortal] failed to notify doctor_id=%s", doctor_id,
        )


@tasks_router.get("/records/{record_id}", response_model=PatientRecordDetailOut)
async def get_patient_record_detail(
    record_id: int,
    authorization: Optional[str] = Header(default=None),
):
    """Return a single record with diagnosis status and treatment plan (if confirmed)."""
    patient = await _authenticate_patient(authorization)

    async with AsyncSessionLocal() as db:
        # Fetch the record, scoped to this patient
        record = (await db.execute(
            select(MedicalRecordDB)
            .where(
                MedicalRecordDB.id == record_id,
                MedicalRecordDB.patient_id == patient.id,
            )
        )).scalar_one_or_none()

        if record is None:
            raise HTTPException(status_code=404, detail="Record not found")

        # DiagnosisResult table removed — diagnosis data now lives in MedicalRecordDB columns
        diagnosis_status: Optional[str] = None
        treatment_plan: Optional[Dict[str, Any]] = None

    safe_create_task(audit(
        "patient", "READ",
        resource_type="patient_record_detail", resource_id=str(record_id),
    ))
    return PatientRecordDetailOut(
        id=record.id,
        record_type=record.record_type,
        content=record.content,
        structured=record.structured_dict() if record.has_structured_data() else None,
        status=record.status,
        created_at=record.created_at,
        diagnosis_status=diagnosis_status,
        treatment_plan=treatment_plan,
    )
