"""Dual-track learning pipeline: style → PersonaPendingItem, factual → KbPendingItem."""

from __future__ import annotations

import json
import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.persona_pending import PersonaPendingItem
from db.models.kb_pending import KbPendingItem
from domain.knowledge.persona_classifier import (
    ClassifyResult,
    LearningType,
    classify_edit,
    compute_kb_pattern_hash,
    compute_pattern_hash,
)
from domain.knowledge.pending_common import (
    is_pattern_suppressed,
    savepoint_insert_pending,
    scrub_pii,
)
from utils.log import log


FACT_LEARNING_ENABLED = os.getenv("FACT_LEARNING_ENABLED", "1") == "1"


async def process_edit_for_learning(
    session: AsyncSession,
    doctor_id: str,
    original: str,
    edited: str,
    edit_id: int,
) -> Optional[ClassifyResult]:
    """Classify a doctor edit and route to the matching pending track."""
    result = await classify_edit(original, edited)
    if not result:
        return None

    if result.type == LearningType.style:
        return await _route_to_persona_pending(session, doctor_id, result, edit_id)
    if result.type == LearningType.factual:
        if not FACT_LEARNING_ENABLED:
            log(f"[learning] edit={edit_id} fact routing disabled by flag, skipping")
            return None
        return await _route_to_kb_pending(session, doctor_id, result, edit_id)
    # context_specific — intentionally drop
    log(f"[learning] edit={edit_id} type={result.type.value} skipping")
    return None


async def _route_to_persona_pending(
    session: AsyncSession,
    doctor_id: str,
    result: ClassifyResult,
    edit_id: int,
) -> Optional[ClassifyResult]:
    if result.confidence == "low":
        log(f"[learning] edit={edit_id} style low confidence, skipping")
        return None

    field = result.persona_field.value if result.persona_field else None
    if not field:
        return None
    pattern = compute_pattern_hash(field, result.summary)

    if await is_pattern_suppressed(session, PersonaPendingItem, doctor_id, pattern):
        log(f"[learning] edit={edit_id} persona pattern suppressed, skipping")
        return None

    def _factory():
        return PersonaPendingItem(
            doctor_id=doctor_id,
            field=field,
            proposed_rule=result.summary,
            summary=result.summary,
            evidence_summary=result.summary,
            evidence_edit_ids=json.dumps([edit_id]),
            confidence=result.confidence,
            pattern_hash=pattern,
        )

    row = await savepoint_insert_pending(session, PersonaPendingItem, doctor_id, pattern, _factory)
    if row is not None:
        log(f"[learning] edit={edit_id} created persona pending id={row.id}")
    return result


async def _route_to_kb_pending(
    session: AsyncSession,
    doctor_id: str,
    result: ClassifyResult,
    edit_id: int,
) -> Optional[ClassifyResult]:
    category = result.kb_category.value if result.kb_category else None
    if not category:
        return None

    scrubbed_rule = scrub_pii(result.proposed_kb_rule)
    scrubbed_summary = scrub_pii(result.summary)
    scrubbed_evidence = scrub_pii(result.summary)

    if len(scrubbed_rule.strip()) < 10:
        log(f"[learning] edit={edit_id} kb rule too short after scrub, skipping")
        return None

    pattern = compute_kb_pattern_hash(category, scrubbed_summary)

    if await is_pattern_suppressed(session, KbPendingItem, doctor_id, pattern):
        log(f"[learning] edit={edit_id} kb pattern suppressed, skipping")
        return None

    def _factory():
        return KbPendingItem(
            doctor_id=doctor_id,
            category=category,
            proposed_rule=scrubbed_rule,
            summary=scrubbed_summary,
            evidence_summary=scrubbed_evidence,
            evidence_edit_ids=json.dumps([edit_id]),
            confidence=result.confidence,
            pattern_hash=pattern,
        )

    row = await savepoint_insert_pending(session, KbPendingItem, doctor_id, pattern, _factory)
    if row is not None:
        log(
            f"[learning] edit={edit_id} type=factual category={category} "
            f"confidence={result.confidence} kb_pending_id={row.id}"
        )
    return result


# Backwards-compat shim — remove after Task 10 renames the caller.
process_edit_for_persona = process_edit_for_learning
