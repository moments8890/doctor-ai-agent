"""Persona pending items API — list, accept, and reject micro-learning suggestions."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.persona_pending import PersonaPendingItem
from db.crud.persona import (
    get_or_create_persona,
    add_rule_to_persona,
    generate_rule_id,
)

router = APIRouter(tags=["ui"], include_in_schema=False)

VALID_FIELDS = {"reply_style", "closing", "structure", "avoid", "edits"}


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/api/manage/persona/pending")
async def list_pending_items(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return all pending persona learning items for the doctor."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(PersonaPendingItem).where(
            PersonaPendingItem.doctor_id == resolved,
            PersonaPendingItem.status == "pending",
        ).order_by(PersonaPendingItem.created_at.desc())
    )
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": item.id,
                "field": item.field,
                "proposed_rule": item.proposed_rule,
                "summary": item.summary,
                "evidence_summary": item.evidence_summary,
                "confidence": item.confidence,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
        "count": len(items),
    }


@router.post("/api/manage/persona/pending/{item_id}/accept")
async def accept_pending_item(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Accept a pending persona suggestion and add it as a rule."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(PersonaPendingItem).where(PersonaPendingItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Pending item not found")
    if item.doctor_id != resolved:
        raise HTTPException(403, "Not authorized")

    rule = {
        "id": generate_rule_id(),
        "text": item.proposed_rule,
        "source": "edit",
        "usage_count": 0,
    }

    if item.field not in VALID_FIELDS:
        raise HTTPException(400, f"Pending item has invalid field: {item.field!r}")

    persona = await get_or_create_persona(session, resolved)
    add_rule_to_persona(persona, item.field, rule)

    if persona.status == "draft":
        persona.status = "active"

    item.status = "accepted"

    await session.commit()
    return {"status": "ok", "rule": rule}


@router.post("/api/manage/persona/pending/{item_id}/reject")
async def reject_pending_item(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Reject a pending persona suggestion."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(PersonaPendingItem).where(PersonaPendingItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Pending item not found")
    if item.doctor_id != resolved:
        raise HTTPException(403, "Not authorized")

    item.status = "rejected"

    await session.commit()
    return {"status": "ok"}
