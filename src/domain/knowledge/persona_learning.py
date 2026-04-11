"""Micro-learning pipeline: classify edit -> check suppression -> create pending item."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.persona_pending import PersonaPendingItem
from domain.knowledge.persona_classifier import classify_edit, compute_pattern_hash
from utils.log import log


async def process_edit_for_persona(
    session: AsyncSession,
    doctor_id: str,
    original: str,
    edited: str,
    edit_id: int,
) -> dict | None:
    """Process a doctor edit through the persona learning pipeline.

    Returns the classification result if a pending item was created, None otherwise.
    """
    # 1. Classify the edit
    result = await classify_edit(original, edited)
    if not result:
        return None

    if result["type"] != "style":
        log(f"[persona_learning] edit {edit_id}: type={result['type']}, skipping")
        return None
    if result.get("confidence") == "low":
        log(f"[persona_learning] edit {edit_id}: low confidence, skipping")
        return None

    field = result.get("persona_field")
    if not field:
        return None

    summary = result.get("summary", "")
    pattern = compute_pattern_hash(field, summary)

    # 2. Check suppression (rejected in last 90 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    suppressed = (await session.execute(
        select(func.count()).select_from(PersonaPendingItem).where(
            PersonaPendingItem.doctor_id == doctor_id,
            PersonaPendingItem.pattern_hash == pattern,
            PersonaPendingItem.status == "rejected",
            PersonaPendingItem.updated_at > cutoff,
        )
    )).scalar() or 0

    if suppressed > 0:
        log(f"[persona_learning] edit {edit_id}: pattern suppressed, skipping")
        return None

    # 3. Check for duplicate pending
    existing = (await session.execute(
        select(func.count()).select_from(PersonaPendingItem).where(
            PersonaPendingItem.doctor_id == doctor_id,
            PersonaPendingItem.pattern_hash == pattern,
            PersonaPendingItem.status == "pending",
        )
    )).scalar() or 0

    if existing > 0:
        log(f"[persona_learning] edit {edit_id}: duplicate pending, skipping")
        return None

    # 4. Create pending item
    pending = PersonaPendingItem(
        doctor_id=doctor_id,
        field=field,
        proposed_rule=summary,
        summary=summary,
        evidence_summary=result.get("summary", ""),
        evidence_edit_ids=json.dumps([edit_id]),
        confidence=result.get("confidence", "medium"),
        pattern_hash=pattern,
    )
    session.add(pending)
    await session.flush()
    log(f"[persona_learning] created pending item {pending.id} for edit {edit_id}")
    return result
