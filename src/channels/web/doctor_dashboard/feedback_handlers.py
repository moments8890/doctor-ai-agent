"""AI feedback capture endpoint — F1 explicit flag only.

Phase F1 of docs/specs/2026-04-21-ai-feedback-capture-plan.md. One endpoint:
POST /api/doctor/feedback → UPDATEs the target ``ai_suggestions`` row with
three feedback columns. Behavior log (F2), digest (F3), and prompt_version
(F4) will add sibling endpoints.

Reworked per Codex review: feedback is NOT a separate table. It's three
nullable columns on ``ai_suggestions`` (feedback_tag, feedback_note,
feedback_created_at). Absence-flagging ("AI should have suggested X but
didn't") is F1.5 and intentionally not supported here — ``suggestion_id``
is required.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.ai_suggestion import (
    AISuggestion,
    FeedbackDoctorAction,
    FeedbackReasonTag,
)
from infra.auth.rate_limit import enforce_doctor_rate_limit

router = APIRouter(tags=["ui"], include_in_schema=False)


# Server-side cap for free-text feedback note. Beyond this we silently
# truncate — this is a feedback surface, not a validation surface.
_FEEDBACK_NOTE_MAX = 1000


class FeedbackRequest(BaseModel):
    # `section` is intentionally absent — it's derived server-side from the
    # suggestion row we look up (keeps client/server in sync automatically).
    suggestion_id: int
    record_id: int
    doctor_id: str
    reason_tag: str
    reason_text: Optional[str] = None
    doctor_action: Optional[str] = None


@router.post("/api/doctor/feedback", include_in_schema=True)
async def submit_feedback(
    body: FeedbackRequest,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Record a doctor's feedback flag by updating the target suggestion row.

    Validates reason_tag against ``FeedbackReasonTag`` (422 on invalid).
    ``reason_text`` beyond _FEEDBACK_NOTE_MAX chars is silently truncated.
    ``doctor_action``, when supplied, must match ``FeedbackDoctorAction`` —
    we currently only use it to validate the payload; the terminal
    doctor-action lives on the existing ``decision`` column.

    Returns 404 if suggestion_id doesn't exist; 403 if it belongs to a
    different doctor than the authenticated caller.
    """
    resolved = _resolve_ui_doctor_id(body.doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.feedback")

    # Validate reason_tag
    try:
        reason_enum = FeedbackReasonTag(body.reason_tag)
    except ValueError:
        allowed = [r.value for r in FeedbackReasonTag]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid reason_tag: '{body.reason_tag}'. Allowed: {allowed}",
        )

    # Validate doctor_action (if present) — silently drop if invalid enum;
    # this field is telemetry-only and we don't want bad clients to block
    # the core feedback event.
    if body.doctor_action is not None:
        try:
            FeedbackDoctorAction(body.doctor_action)
        except ValueError:
            pass  # swallow — not persisted into a dedicated column anyway

    # Truncate note silently (UX spec: "truncate server-side to 1000 chars if
    # longer, no error"). Preserve None vs empty string.
    note_value: Optional[str] = body.reason_text
    if note_value is not None and len(note_value) > _FEEDBACK_NOTE_MAX:
        note_value = note_value[:_FEEDBACK_NOTE_MAX]

    # Look up the target suggestion row.
    row = (
        await db.execute(
            select(AISuggestion).where(AISuggestion.id == body.suggestion_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"suggestion_id {body.suggestion_id} not found",
        )
    if row.doctor_id != resolved:
        raise HTTPException(
            status_code=403,
            detail="suggestion belongs to a different doctor",
        )

    now = datetime.utcnow()
    row.feedback_tag = reason_enum.value
    row.feedback_note = note_value
    row.feedback_created_at = now
    await db.commit()
    await db.refresh(row)

    return {
        "id": row.id,
        "created_at": (
            row.feedback_created_at.isoformat()
            if row.feedback_created_at
            else None
        ),
    }
