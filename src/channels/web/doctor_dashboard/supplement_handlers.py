"""Doctor-side actions on RecordSupplementDB rows. Spec §5b Edge case 2."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.engine import get_db
from db.models.records import MedicalRecordDB, RecordSupplementDB, FieldEntryDB
from domain.patient_lifecycle.dedup import REQUIRED_FIELDS

router = APIRouter(tags=["ui"], include_in_schema=False)


async def _load_supplement_for_doctor(
    session: AsyncSession,
    supplement_id: int,
    doctor_id: str,
) -> RecordSupplementDB:
    """Load a pending supplement and verify it belongs to the requesting doctor."""
    sup = await session.get(RecordSupplementDB, supplement_id)
    if not sup or sup.status != "pending_doctor_review":
        raise HTTPException(status_code=404)
    rec = await session.get(MedicalRecordDB, sup.record_id)
    if not rec or rec.doctor_id != doctor_id:
        raise HTTPException(status_code=404)
    return sup


@router.get("/api/manage/supplements/pending")
async def list_pending(
    doctor_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.execute(
            select(RecordSupplementDB)
            .join(MedicalRecordDB, MedicalRecordDB.id == RecordSupplementDB.record_id)
            .where(
                RecordSupplementDB.status == "pending_doctor_review",
                MedicalRecordDB.doctor_id == doctor_id,
            )
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": s.id,
                "record_id": s.record_id,
                "field_entries": json.loads(s.field_entries_json),
                "created_at": s.created_at.isoformat(),
            }
            for s in rows
        ]
    }


@router.post("/api/manage/supplements/{supplement_id}/accept")
async def accept(
    supplement_id: int,
    doctor_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    sup = await _load_supplement_for_doctor(session, supplement_id, doctor_id)
    entries = json.loads(sup.field_entries_json)
    for e in entries:
        if e["field_name"] not in REQUIRED_FIELDS:
            continue
        session.add(
            FieldEntryDB(
                record_id=sup.record_id,
                field_name=e["field_name"],
                text=e["text"],
                intake_segment_id=e.get("intake_segment_id"),
                created_at=datetime.fromisoformat(e["created_at"]),
            )
        )
    sup.status = "accepted"
    sup.doctor_decision_at = datetime.utcnow()
    sup.doctor_decision_by = doctor_id
    await session.commit()
    return {"id": supplement_id, "status": "accepted"}


@router.post("/api/manage/supplements/{supplement_id}/create_new")
async def create_new(
    supplement_id: int,
    doctor_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    sup = await _load_supplement_for_doctor(session, supplement_id, doctor_id)
    sup.status = "rejected_create_new"
    sup.doctor_decision_at = datetime.utcnow()
    sup.doctor_decision_by = doctor_id
    # NOTE: actual new-record forking deferred to follow-up. The status flip is the
    # signal for the frontend to navigate the doctor to new-record creation.
    await session.commit()
    return {"id": supplement_id, "status": "rejected_create_new"}


@router.post("/api/manage/supplements/{supplement_id}/ignore")
async def ignore(
    supplement_id: int,
    doctor_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    sup = await _load_supplement_for_doctor(session, supplement_id, doctor_id)
    sup.status = "rejected_ignored"
    sup.doctor_decision_at = datetime.utcnow()
    sup.doctor_decision_by = doctor_id
    await session.commit()
    return {"id": supplement_id, "status": "rejected_ignored"}
