"""Knowledge usage stats API for the doctor management UI."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, Query

from channels.web.ui._utils import _resolve_ui_doctor_id
from db.engine import AsyncSessionLocal
from domain.knowledge.usage_tracking import get_knowledge_stats, get_recent_activity

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/knowledge/stats")
async def knowledge_stats(
    doctor_id: str = Query(...),
    days: int = Query(7, ge=1, le=365),
    authorization: Optional[str] = Header(default=None),
):
    """Return per-knowledge-item usage counts for the last N days."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as session:
        stats = await get_knowledge_stats(session, resolved, days=days)
    return {"stats": stats}


@router.get("/api/manage/knowledge/activity")
async def knowledge_activity(
    doctor_id: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
):
    """Return recent knowledge usage log entries."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    async with AsyncSessionLocal() as session:
        activity = await get_recent_activity(session, resolved, limit=limit)
    return {"activity": activity}
