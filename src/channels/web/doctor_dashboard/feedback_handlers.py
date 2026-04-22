"""AI feedback capture endpoints — F1 explicit flag + F3 doctor digest.

Phase F1/F3 of docs/specs/2026-04-21-ai-feedback-capture-plan.md. Two
endpoints:
- POST /api/doctor/feedback → UPDATEs the target ``ai_suggestions`` row
  with three feedback columns (F1).
- GET  /api/doctor/feedback/digest → aggregates shown / accepted /
  flagged counts over the last ``days`` window plus a recent-flag list
  for the MyAIPage "你的 AI 表现" card (F3).

Reworked per Codex review: feedback is NOT a separate table. It's three
nullable columns on ``ai_suggestions`` (feedback_tag, feedback_note,
feedback_created_at). Absence-flagging ("AI should have suggested X but
didn't") is F1.5 and intentionally not supported here — ``suggestion_id``
is required.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.ai_suggestion import (
    AISuggestion,
    FeedbackDoctorAction,
    FeedbackReasonTag,
)
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.events import log_event

router = APIRouter(tags=["ui"], include_in_schema=False)


# F3 digest: hard cap on the lookback window so clients can't ask for a
# ridiculous range. 90 days matches the ai_behavior_event retention spec.
_DIGEST_MAX_DAYS = 90
_DIGEST_DEFAULT_DAYS = 7
_DIGEST_RECENT_LIMIT = 10

# Section values surfaced on the breakdown — rendered as 0-rows even when
# empty so the card stays visually stable across doctors. Enum values
# mirror ``SuggestionSection`` but are kept as a local tuple because the
# digest renders them in a specific UI order, not whatever the enum emits.
_DIGEST_SECTIONS: tuple[str, ...] = ("differential", "workup", "treatment")

# The set of ``decision`` values that count as "accepted" for the digest.
# ``rejected`` is excluded on purpose — rejecting is also a terminal decision
# but for this card we want "did the doctor keep the AI's output in some
# form", which is confirmed/edited/custom. "pending"/None means the row was
# shown but not yet resolved.
_ACCEPTED_DECISIONS: tuple[str, ...] = ("confirmed", "edited", "custom")


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

    log_event(
        "feedback.flagged",
        suggestion_id=row.id,
        record_id=body.record_id,
        doctor_id=resolved,
        reason_tag=reason_enum.value,
        note_len=len(note_value) if note_value else 0,
        section=row.section,
    )
    return {
        "id": row.id,
        "created_at": (
            row.feedback_created_at.isoformat()
            if row.feedback_created_at
            else None
        ),
    }


@router.get("/api/doctor/feedback/digest", include_in_schema=True)
async def get_feedback_digest(
    doctor_id: Optional[str] = Query(default=None),
    days: int = Query(default=_DIGEST_DEFAULT_DAYS, ge=1, le=_DIGEST_MAX_DAYS),
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return weekly-style AI performance digest for the MyAIPage card.

    Uses SQL-level aggregates (not ORM-per-row) to stay cheap at scale. The
    "flagged" counts key off ``feedback_created_at`` — flag time is more
    honest than the suggestion's original ``created_at`` when the doctor
    flags an older case.

    The breakdown dict is filled with 0s for missing sections so the
    frontend doesn't have to reconcile schema drift.
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.feedback.digest")

    cutoff = datetime.utcnow() - timedelta(days=days)

    # 1) total_shown — suggestions emitted to this doctor in window
    total_shown = (
        await db.execute(
            select(func.count(AISuggestion.id)).where(
                AISuggestion.doctor_id == resolved,
                AISuggestion.created_at >= cutoff,
            )
        )
    ).scalar_one()

    # 2) total_accepted — doctor kept the AI output (confirmed/edited/custom)
    total_accepted = (
        await db.execute(
            select(func.count(AISuggestion.id)).where(
                AISuggestion.doctor_id == resolved,
                AISuggestion.created_at >= cutoff,
                AISuggestion.decision.in_(_ACCEPTED_DECISIONS),
            )
        )
    ).scalar_one()

    # 3) total_flagged — count of rows whose feedback landed in window
    total_flagged = (
        await db.execute(
            select(func.count(AISuggestion.id)).where(
                AISuggestion.doctor_id == resolved,
                AISuggestion.feedback_tag.is_not(None),
                AISuggestion.feedback_created_at >= cutoff,
            )
        )
    ).scalar_one()

    # 4) breakdown by section — render all 3 sections even when 0
    breakdown_rows = (
        await db.execute(
            select(AISuggestion.section, func.count(AISuggestion.id))
            .where(
                AISuggestion.doctor_id == resolved,
                AISuggestion.feedback_tag.is_not(None),
                AISuggestion.feedback_created_at >= cutoff,
            )
            .group_by(AISuggestion.section)
        )
    ).all()
    by_section: dict[str, int] = {s: 0 for s in _DIGEST_SECTIONS}
    for section, count in breakdown_rows:
        # Tolerate unexpected section values instead of dropping them; keeps
        # the total honest if a migration adds a new section we don't know.
        by_section[section] = int(count)

    # 5) recent 10 flags with patient name (LEFT JOIN — record_id may not
    # have an associated patient, and patient row may have been deleted)
    recent_rows = (
        await db.execute(
            select(
                AISuggestion.id,
                AISuggestion.section,
                AISuggestion.content,
                AISuggestion.edited_text,
                AISuggestion.feedback_tag,
                AISuggestion.feedback_note,
                AISuggestion.feedback_created_at,
                Patient.name,
            )
            .select_from(AISuggestion)
            .join(
                MedicalRecordDB,
                MedicalRecordDB.id == AISuggestion.record_id,
                isouter=True,
            )
            .join(
                Patient,
                Patient.id == MedicalRecordDB.patient_id,
                isouter=True,
            )
            .where(
                AISuggestion.doctor_id == resolved,
                AISuggestion.feedback_tag.is_not(None),
                AISuggestion.feedback_created_at >= cutoff,
            )
            .order_by(AISuggestion.feedback_created_at.desc())
            .limit(_DIGEST_RECENT_LIMIT)
        )
    ).all()

    recent = [
        {
            "id": r[0],
            "section": r[1],
            "content": r[2],
            "edited_text": r[3],
            "feedback_tag": r[4],
            "feedback_note": r[5],
            "feedback_created_at": r[6].isoformat() if r[6] else None,
            "patient_name": r[7],
        }
        for r in recent_rows
    ]

    return {
        "days": days,
        "total_shown": int(total_shown),
        "total_accepted": int(total_accepted),
        "total_flagged": int(total_flagged),
        "by_section": by_section,
        "recent": recent,
    }
