"""Platform-level feedback capture (open-ended "this app is broken / I want X").

Distinct from `feedback_handlers.py`, which captures per-AISuggestion flags
(reason_tag + reason_note keyed to a specific suggestion row). This module
takes a single free-text blob and writes it to a dedicated `platform_feedback`
table so beta operators can `SELECT * ORDER BY created_at DESC` and read what
partner doctors are saying about the platform itself.

Auth: requires a valid doctor JWT (Authorization: Bearer ...). Anonymous
submission is intentionally not supported — we want a real doctor_id so
follow-up conversations are possible.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import Doctor, PlatformFeedback
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.auth.unified import authenticate
from infra.observability.events import log_event


router = APIRouter(tags=["ui"], include_in_schema=False)

# Hard cap on submitted text. Anything beyond this is silently truncated —
# we never want a 422 to swallow real signal. Generous enough to cover a
# detailed bug report with reproduction steps.
_FEEDBACK_CONTENT_MAX = 4000

# Header strings ("page_url" / "user_agent") get bounded to fit the column.
_PAGE_URL_MAX = 512
_USER_AGENT_MAX = 512


class PlatformFeedbackRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=_FEEDBACK_CONTENT_MAX + 1000)
    page_url: Optional[str] = Field(default=None, max_length=_PAGE_URL_MAX + 100)
    user_agent: Optional[str] = Field(default=None, max_length=_USER_AGENT_MAX + 100)


def _trunc(value: Optional[str], n: int) -> Optional[str]:
    if value is None:
        return None
    return value if len(value) <= n else value[:n]


@router.post("/api/platform/feedback", include_in_schema=True)
async def submit_platform_feedback(
    body: PlatformFeedbackRequest,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Insert a row into `platform_feedback` keyed to the authenticated doctor."""
    payload = await authenticate(authorization)
    doctor_id = payload.get("doctor_id")
    if not doctor_id:
        raise HTTPException(
            status_code=401,
            detail="Authenticated doctor session required for platform feedback.",
        )
    enforce_doctor_rate_limit(doctor_id, scope="ui.platform_feedback")

    content = body.content.strip()
    if not content:
        raise HTTPException(
            status_code=422,
            detail="content is required (whitespace-only strings rejected).",
        )
    content = _trunc(content, _FEEDBACK_CONTENT_MAX)

    # Best-effort name lookup — we cache the display name on the row so the
    # admin reader doesn't have to JOIN against doctors when the FK target
    # has been deleted.
    doctor_row = (
        await db.execute(select(Doctor).where(Doctor.doctor_id == doctor_id))
    ).scalar_one_or_none()
    display_name = doctor_row.name if doctor_row else None

    row = PlatformFeedback(
        doctor_id=doctor_id,
        doctor_display_name=display_name,
        content=content,
        page_url=_trunc(body.page_url, _PAGE_URL_MAX),
        user_agent=_trunc(body.user_agent, _USER_AGENT_MAX),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    log_event(
        "platform_feedback.submitted",
        feedback_id=row.id,
        doctor_id=doctor_id,
        page_url=row.page_url,
        content_length=len(content),
    )

    return {"id": row.id, "ok": True}
