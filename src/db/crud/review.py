"""CRUD operations for the review queue."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MedicalRecordDB, MedicalRecordVersion, Patient
from db.models.interview_session import InterviewSessionDB
from db.models.review_queue import ReviewQueue
from db.models.base import _utcnow
from domain.records.schema import FIELD_KEYS


async def create_review(
    session: AsyncSession,
    record_id: int,
    doctor_id: str,
    patient_id: Optional[int],
) -> ReviewQueue:
    """Insert a new review queue entry."""
    entry = ReviewQueue(
        record_id=record_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        status="pending_review",
        created_at=_utcnow(),
    )
    session.add(entry)
    return entry


async def list_reviews(
    session: AsyncSession,
    doctor_id: str,
    status: str = "pending_review",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List review queue entries with patient name and chief complaint."""
    q = (
        select(ReviewQueue, Patient.name, MedicalRecordDB.structured, MedicalRecordDB.created_at)
        .outerjoin(Patient, ReviewQueue.patient_id == Patient.id)
        .join(MedicalRecordDB, ReviewQueue.record_id == MedicalRecordDB.id)
        .where(ReviewQueue.doctor_id == doctor_id, ReviewQueue.status == status)
    )
    if status == "reviewed":
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        q = q.where(ReviewQueue.reviewed_at >= cutoff)
    q = q.order_by(ReviewQueue.created_at.desc()).limit(limit)
    result = await session.execute(q)
    rows = result.all()
    items = []
    for rq, patient_name, structured_json, record_created_at in rows:
        structured = json.loads(structured_json) if structured_json else {}
        chief = structured.get("chief_complaint", "")
        items.append({
            "id": rq.id,
            "record_id": rq.record_id,
            "patient_id": rq.patient_id,
            "patient_name": patient_name or "",
            "chief_complaint": chief[:60] if chief else "",
            "status": rq.status,
            "created_at": rq.created_at.isoformat() if rq.created_at else None,
            "reviewed_at": rq.reviewed_at.isoformat() if rq.reviewed_at else None,
        })
    return items


async def get_review_detail(
    session: AsyncSession,
    queue_id: int,
    doctor_id: str,
) -> Optional[Dict[str, Any]]:
    """Get full review detail: structured record + interview chat history."""
    rq = (await session.execute(
        select(ReviewQueue).where(
            ReviewQueue.id == queue_id,
            ReviewQueue.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if rq is None:
        return None

    record = (await session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == rq.record_id)
    )).scalar_one_or_none()
    if record is None:
        return None

    patient = None
    if rq.patient_id:
        patient = (await session.execute(
            select(Patient).where(Patient.id == rq.patient_id)
        )).scalar_one_or_none()

    # Get interview conversation
    conversation = []
    if rq.patient_id:
        interview = (await session.execute(
            select(InterviewSessionDB)
            .where(
                InterviewSessionDB.patient_id == rq.patient_id,
                InterviewSessionDB.doctor_id == doctor_id,
                InterviewSessionDB.status == "completed",
            )
            .order_by(InterviewSessionDB.updated_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if interview and interview.conversation:
            conversation = json.loads(interview.conversation)

    structured = json.loads(record.structured) if record.structured else {}
    tags = json.loads(record.tags) if record.tags else []

    return {
        "id": rq.id,
        "record_id": rq.record_id,
        "status": rq.status,
        "created_at": rq.created_at.isoformat() if rq.created_at else None,
        "reviewed_at": rq.reviewed_at.isoformat() if rq.reviewed_at else None,
        "patient": {
            "id": patient.id if patient else None,
            "name": patient.name if patient else "",
            "gender": patient.gender if patient else None,
            "year_of_birth": patient.year_of_birth if patient else None,
        } if patient else None,
        "record": {
            "id": record.id,
            "record_type": record.record_type,
            "content": record.content,
            "structured": structured,
            "tags": tags,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        },
        "conversation": conversation,
    }


async def confirm_review(
    session: AsyncSession,
    queue_id: int,
    doctor_id: str,
) -> Optional[ReviewQueue]:
    """Mark a review as confirmed."""
    rq = (await session.execute(
        select(ReviewQueue).where(
            ReviewQueue.id == queue_id,
            ReviewQueue.doctor_id == doctor_id,
            ReviewQueue.status == "pending_review",
        )
    )).scalar_one_or_none()
    if rq is None:
        return None
    rq.status = "reviewed"
    rq.reviewed_at = _utcnow()
    return rq


async def update_review_field(
    session: AsyncSession,
    queue_id: int,
    doctor_id: str,
    field: str,
    value: str,
) -> Optional[Dict[str, Any]]:
    """Update a single structured field on the underlying medical record."""
    if field not in FIELD_KEYS:
        return None  # caller should raise 422

    rq = (await session.execute(
        select(ReviewQueue).where(
            ReviewQueue.id == queue_id,
            ReviewQueue.doctor_id == doctor_id,
        )
    )).scalar_one_or_none()
    if rq is None:
        return None

    record = (await session.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == rq.record_id)
    )).scalar_one_or_none()
    if record is None:
        return None

    # Snapshot for audit
    version = MedicalRecordVersion(
        record_id=record.id,
        doctor_id=doctor_id,
        old_content=record.content,
        old_tags=record.tags,
        old_record_type=record.record_type,
        old_structured=record.structured,
    )
    session.add(version)

    # Update structured field
    structured = json.loads(record.structured) if record.structured else {}
    structured[field] = value
    record.structured = json.dumps(structured, ensure_ascii=False)
    record.updated_at = _utcnow()

    return {
        "record_id": record.id,
        "structured": structured,
    }
