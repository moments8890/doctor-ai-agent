"""Today Summary endpoint — LLM-generated daily briefing."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from domain.briefing.today_summary import TodaySummaryResponse, get_today_summary
from infra.auth.rate_limit import enforce_doctor_rate_limit
from utils.log import log

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/doctor/today-summary", response_model=TodaySummaryResponse)
async def get_today_summary_api(
    doctor_id: str = Query(default="web_doctor"),
    refresh: bool = Query(default=False),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> TodaySummaryResponse:
    """Return LLM-generated today summary for the doctor home page.

    Lazy-loaded on page view, cached for 30 minutes.
    Pass refresh=true to force regeneration (e.g. pull-to-refresh).
    Never returns 500 — falls back to empty response on any error.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.today_summary")
    try:
        return await get_today_summary(db, doctor_id=resolved, refresh=refresh)
    except Exception as exc:
        log(f"[today_summary] handler error: {exc}", level="warning")
        now = datetime.now(timezone.utc)
        return TodaySummaryResponse(
            mode="empty",
            summary="",
            generated_at=now.isoformat(),
            expires_at=now.isoformat(),
            empty_reason="quiet_day",
        )
