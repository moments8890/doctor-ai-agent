"""Doctor-side actions on RecordSupplementDB rows. Spec §5b Edge case 2."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.engine import get_db
from db.models.records import RecordSupplementDB, FieldEntryDB

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/supplements/pending")
async def list_pending(
    doctor_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    rows = (
        await session.execute(
            select(RecordSupplementDB).where(
                RecordSupplementDB.status == "pending_doctor_review"
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
    sup = await session.get(RecordSupplementDB, supplement_id)
    if not sup or sup.status != "pending_doctor_review":
        raise HTTPException(status_code=404)
    entries = json.loads(sup.field_entries_json)
    for e in entries:
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
    sup = await session.get(RecordSupplementDB, supplement_id)
    if not sup or sup.status != "pending_doctor_review":
        raise HTTPException(status_code=404)
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
    sup = await session.get(RecordSupplementDB, supplement_id)
    if not sup or sup.status != "pending_doctor_review":
        raise HTTPException(status_code=404)
    sup.status = "rejected_ignored"
    sup.doctor_decision_at = datetime.utcnow()
    sup.doctor_decision_by = doctor_id
    await session.commit()
    return {"id": supplement_id, "status": "rejected_ignored"}
