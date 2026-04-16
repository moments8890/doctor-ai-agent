"""KB pending items API — list, accept, reject factual-edit suggestions."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.doctor import KnowledgeCategory
from db.models.kb_pending import KbPendingItem
from domain.knowledge.knowledge_crud import save_knowledge_item
from domain.knowledge.knowledge_context import _invalidate_cache
from utils.log import log


router = APIRouter(tags=["ui"], include_in_schema=False)


VALID_CATEGORIES = {c.value for c in KnowledgeCategory}


@router.get("/api/manage/kb/pending")
async def list_pending_items(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(KbPendingItem).where(
            KbPendingItem.doctor_id == resolved,
            KbPendingItem.status == "pending",
        ).order_by(KbPendingItem.created_at.desc())
    )
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": item.id,
                "category": item.category,
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


@router.post("/api/manage/kb/pending/{item_id}/accept")
async def accept_pending_item(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(KbPendingItem).where(KbPendingItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Pending item not found")
    if item.doctor_id != resolved:
        raise HTTPException(403, "Not authorized")
    if item.status != "pending":
        raise HTTPException(409, f"Item already {item.status}")
    if item.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Invalid category: {item.category!r}")

    # save_knowledge_item commits internally — do not wrap in outer txn
    kb_item = await save_knowledge_item(
        session,
        doctor_id=resolved,
        text=item.proposed_rule,
        source="doctor",
        confidence=1.0,
        category=item.category,
        seed_source="edit_fact",
    )
    if kb_item is None:
        raise HTTPException(500, "Failed to save knowledge item")

    item.status = "accepted"
    item.accepted_knowledge_item_id = kb_item.id
    await session.commit()

    _invalidate_cache(resolved)

    log(
        f"[kb_pending] accepted id={item.id} doctor={resolved} "
        f"category={item.category} knowledge_item_id={kb_item.id}"
    )
    return {
        "status": "ok",
        "knowledge_item_id": kb_item.id,
        "title": kb_item.title,
    }


@router.post("/api/manage/kb/pending/{item_id}/reject")
async def reject_pending_item(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    result = await session.execute(
        select(KbPendingItem).where(KbPendingItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(404, "Pending item not found")
    if item.doctor_id != resolved:
        raise HTTPException(403, "Not authorized")
    if item.status != "pending":
        raise HTTPException(409, f"Item already {item.status}")

    item.status = "rejected"
    await session.commit()
    log(f"[kb_pending] rejected id={item.id} doctor={resolved}")
    return {"status": "ok"}
