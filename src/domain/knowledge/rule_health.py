"""Compute per-rule health stats by scanning AISuggestion + MessageDraft rows."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ai_suggestion import AISuggestion, SuggestionDecision
from db.models.message_draft import MessageDraft, DraftStatus


def _contains(ids_json: Optional[str], kb_id: int) -> bool:
    if not ids_json:
        return False
    try:
        ids = json.loads(ids_json)
        return isinstance(ids, list) and kb_id in ids
    except (json.JSONDecodeError, TypeError):
        return False


def _is_recent(created_at: Optional[datetime], cutoff: datetime) -> bool:
    if not created_at:
        return False
    dt = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=timezone.utc)
    return dt > cutoff


async def compute_rule_health(
    session: AsyncSession,
    doctor_id: str,
    kb_item_id: int,
) -> dict:
    """Return aggregate + last-30-days health stats for a KB rule."""
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)

    # Suggestions
    sug_rows = (await session.execute(
        select(AISuggestion).where(
            AISuggestion.doctor_id == doctor_id,
            AISuggestion.cited_knowledge_ids.is_not(None),
        )
    )).scalars().all()

    # Drafts
    draft_rows = (await session.execute(
        select(MessageDraft).where(
            MessageDraft.doctor_id == doctor_id,
            MessageDraft.cited_knowledge_ids.is_not(None),
        )
    )).scalars().all()

    totals = {"cited": 0, "accepted": 0, "edited": 0, "rejected": 0}
    last30 = {"cited": 0, "accepted": 0, "edited": 0, "rejected": 0}

    for row in sug_rows:
        if not _contains(row.cited_knowledge_ids, kb_item_id):
            continue
        recent = _is_recent(row.created_at, cutoff_30d)
        totals["cited"] += 1
        if recent:
            last30["cited"] += 1
        if row.decision == SuggestionDecision.confirmed.value:
            totals["accepted"] += 1
            if recent:
                last30["accepted"] += 1
        elif row.decision == SuggestionDecision.edited.value:
            totals["edited"] += 1
            if recent:
                last30["edited"] += 1
        elif row.decision == SuggestionDecision.rejected.value:
            totals["rejected"] += 1
            if recent:
                last30["rejected"] += 1

    for row in draft_rows:
        if not _contains(row.cited_knowledge_ids, kb_item_id):
            continue
        recent = _is_recent(row.created_at, cutoff_30d)
        totals["cited"] += 1
        if recent:
            last30["cited"] += 1
        if row.status == DraftStatus.sent.value:
            totals["accepted"] += 1
            if recent:
                last30["accepted"] += 1
        elif row.status == DraftStatus.edited.value:
            totals["edited"] += 1
            if recent:
                last30["edited"] += 1
        elif row.status == DraftStatus.dismissed.value:
            totals["rejected"] += 1
            if recent:
                last30["rejected"] += 1

    return {
        "cited_count": totals["cited"],
        "accepted_count": totals["accepted"],
        "edited_count": totals["edited"],
        "rejected_count": totals["rejected"],
        "last_30_days": {
            "cited_count": last30["cited"],
            "accepted_count": last30["accepted"],
            "edited_count": last30["edited"],
            "rejected_count": last30["rejected"],
        },
    }
