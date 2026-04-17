"""API: recent hallucinated KB citations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.hallucinated_citation import HallucinatedCitation


router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/kb/hallucinations")
async def list_hallucinations(
    doctor_id: str = Query(...),
    days: int = Query(7, ge=1, le=90),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    count = (await session.execute(
        select(func.count()).select_from(HallucinatedCitation).where(
            HallucinatedCitation.doctor_id == resolved,
            HallucinatedCitation.created_at > cutoff,
        )
    )).scalar() or 0

    recent = (await session.execute(
        select(HallucinatedCitation).where(
            HallucinatedCitation.doctor_id == resolved,
            HallucinatedCitation.created_at > cutoff,
        ).order_by(HallucinatedCitation.created_at.desc()).limit(20)
    )).scalars().all()

    return {
        "count": count,
        "days": days,
        "recent": [
            {
                "id": row.id,
                "context": row.context,
                "context_id": row.context_id,
                "hallucinated_id": row.hallucinated_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in recent
        ],
    }
