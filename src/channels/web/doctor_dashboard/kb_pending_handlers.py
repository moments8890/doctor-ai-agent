"""KB pending items API — list, accept, reject factual-edit suggestions."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.ai_suggestion import AISuggestion
from db.models.doctor import KnowledgeCategory
from db.models.doctor_edit import DoctorEdit
from db.models.kb_pending import KbPendingItem
from db.models.message_draft import MessageDraft
from domain.knowledge.knowledge_crud import save_knowledge_item
from domain.knowledge.knowledge_context import _invalidate_cache
from utils.log import log


async def _resolve_source_link(
    session: AsyncSession, evidence_edit_ids_json: Optional[str],
) -> Optional[dict]:
    """Trace evidence_edit_ids → DoctorEdit → MessageDraft/AISuggestion → routable target.

    Returns {entity_type, patient_id?, record_id?} for the UI to build a link,
    or None when the edit chain doesn't resolve.
    """
    if not evidence_edit_ids_json:
        return None
    try:
        edit_ids = json.loads(evidence_edit_ids_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not edit_ids:
        return None

    edit = (await session.execute(
        select(DoctorEdit).where(DoctorEdit.id == int(edit_ids[0]))
    )).scalar_one_or_none()
    if edit is None:
        return None

    if edit.entity_type == "draft_reply":
        draft = (await session.execute(
            select(MessageDraft).where(MessageDraft.id == edit.entity_id)
        )).scalar_one_or_none()
        if draft is None:
            return None
        return {
            "entity_type": "draft_reply",
            "patient_id": draft.patient_id,
            "draft_id": draft.id,
        }
    if edit.entity_type == "diagnosis":
        sug = (await session.execute(
            select(AISuggestion).where(AISuggestion.id == edit.entity_id)
        )).scalar_one_or_none()
        if sug is None:
            return None
        return {
            "entity_type": "diagnosis",
            "record_id": sug.record_id,
            "suggestion_id": sug.id,
        }
    return None


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

    payload = []
    for item in items:
        source_link = await _resolve_source_link(session, item.evidence_edit_ids)
        payload.append({
            "id": item.id,
            "category": item.category,
            "proposed_rule": item.proposed_rule,
            "summary": item.summary,
            "evidence_summary": item.evidence_summary,
            "confidence": item.confidence,
            "status": item.status,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "source_link": source_link,
        })

    return {"items": payload, "count": len(payload)}


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


class _TestSeedKbPendingPayload(BaseModel):
    category: str
    proposed_rule: str
    summary: str = ""
    confidence: str = "medium"


@router.post("/api/test/seed/kb-pending")
async def test_seed_kb_pending(
    payload: _TestSeedKbPendingPayload,
    doctor_id: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    """Test/dev only: insert a KbPendingItem for a doctor. Gated by ENVIRONMENT."""
    _env = os.environ.get("ENVIRONMENT", "").strip().lower()
    if _env not in ("development", "dev", "test") and "pytest" not in sys.modules:
        raise HTTPException(status_code=404)

    summary = payload.summary or payload.proposed_rule[:60]
    ph = hashlib.md5((payload.category + payload.proposed_rule).encode()).hexdigest()[:16]

    pending = KbPendingItem(
        doctor_id=doctor_id,
        category=payload.category,
        proposed_rule=payload.proposed_rule,
        summary=summary,
        evidence_summary=summary,
        confidence=payload.confidence,
        pattern_hash=ph,
    )
    session.add(pending)
    await session.commit()
    await session.refresh(pending)
    log(f"[kb_pending] test-seeded id={pending.id} doctor={doctor_id}")
    return {"id": pending.id}


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
