from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.crud import get_approval_item, list_approval_items
from db.engine import AsyncSessionLocal
from db.models import ApprovalItem
from services.approval import commit_approval, reject_approval

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ApprovalItemOut(BaseModel):
    id: int
    doctor_id: str
    item_type: str
    status: str
    suggested_data: dict
    source_text: Optional[str]
    patient_id: Optional[int]
    record_id: Optional[int]
    reviewer_note: Optional[str]
    reviewed_at: Optional[str]  # ISO 8601
    created_at: str             # ISO 8601


class ApproveRequest(BaseModel):
    edited_data: Optional[dict] = None
    reviewer_note: Optional[str] = None


class RejectRequest(BaseModel):
    reviewer_note: Optional[str] = None


def _to_out(item: ApprovalItem) -> ApprovalItemOut:
    try:
        suggested = json.loads(item.suggested_data)
    except (json.JSONDecodeError, TypeError):
        suggested = {}
    return ApprovalItemOut(
        id=item.id,
        doctor_id=item.doctor_id,
        item_type=item.item_type,
        status=item.status,
        suggested_data=suggested,
        source_text=item.source_text,
        patient_id=item.patient_id,
        record_id=item.record_id,
        reviewer_note=item.reviewer_note,
        reviewed_at=item.reviewed_at.isoformat() if item.reviewed_at else None,
        created_at=item.created_at.isoformat(),
    )


@router.get("", response_model=List[ApprovalItemOut])
async def list_approvals(doctor_id: str, status: Optional[str] = None):
    """List approval items for a doctor, optionally filtered by status."""
    async with AsyncSessionLocal() as db:
        items = await list_approval_items(db, doctor_id, status=status)
    return [_to_out(i) for i in items]


@router.get("/{approval_id}", response_model=ApprovalItemOut)
async def get_approval(approval_id: int, doctor_id: str):
    """Retrieve a single approval item."""
    async with AsyncSessionLocal() as db:
        item = await get_approval_item(db, approval_id, doctor_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Approval #{approval_id} not found.")
    return _to_out(item)


@router.patch("/{approval_id}/approve", response_model=ApprovalItemOut)
async def approve_item(approval_id: int, doctor_id: str, body: ApproveRequest):
    """Approve a pending item and commit the medical record to the database."""
    try:
        item = await commit_approval(
            approval_id,
            doctor_id,
            edited_data=body.edited_data,
            reviewer_note=body.reviewer_note,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    return _to_out(item)


@router.patch("/{approval_id}/reject", response_model=ApprovalItemOut)
async def reject_item(approval_id: int, doctor_id: str, body: RejectRequest):
    """Reject a pending item. No record is written to the database."""
    try:
        item = await reject_approval(
            approval_id,
            doctor_id,
            reviewer_note=body.reviewer_note,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    return _to_out(item)
