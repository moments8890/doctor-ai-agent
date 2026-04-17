"""Knowledge usage stats API for the doctor management UI."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from domain.knowledge.usage_tracking import get_knowledge_stats, get_recent_activity

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/knowledge/stats")
async def knowledge_stats(
    doctor_id: str = Query(...),
    days: int = Query(7, ge=1, le=365),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return per-knowledge-item usage counts for the last N days."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    stats = await get_knowledge_stats(session, resolved, days=days)
    return {"stats": stats}


@router.get("/api/manage/knowledge/{item_id}/usage")
async def knowledge_item_usage(
    item_id: int,
    doctor_id: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return usage history for a single knowledge item."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    from sqlalchemy import desc, select

    from db.models.knowledge_usage import KnowledgeUsageLog

    rows = (
        await session.execute(
            select(KnowledgeUsageLog)
            .where(
                KnowledgeUsageLog.doctor_id == resolved,
                KnowledgeUsageLog.knowledge_item_id == item_id,
            )
            .order_by(desc(KnowledgeUsageLog.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return {
        "usage": [
            {
                "id": r.id,
                "usage_context": r.usage_context,
                "patient_id": r.patient_id,
                "record_id": r.record_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.get("/api/manage/knowledge/activity")
async def knowledge_activity(
    doctor_id: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return recent knowledge usage log entries."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    activity = await get_recent_activity(session, resolved, limit=limit)
    return {"activity": activity}


@router.get("/api/manage/knowledge/{item_id}/health")
async def get_rule_health(
    item_id: int,
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return AI citation + decision stats for a single knowledge rule."""
    from domain.knowledge.rule_health import compute_rule_health

    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    return await compute_rule_health(session, resolved, item_id)
