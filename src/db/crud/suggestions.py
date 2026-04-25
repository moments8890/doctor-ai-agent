"""CRUD for ai_suggestions table."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ai_suggestion import AISuggestion, SuggestionDecision, SuggestionSection
from db.crud._common import _utcnow


async def create_suggestion(
    session: AsyncSession,
    *,
    record_id: int,
    doctor_id: str,
    section: SuggestionSection,
    content: str,
    detail: Optional[str] = None,
    confidence: Optional[str] = None,
    urgency: Optional[str] = None,
    intervention: Optional[str] = None,
    is_custom: bool = False,
    cited_knowledge_ids: Optional[str] = None,
    prompt_hash: Optional[str] = None,
    # 2026-04-25 new schema fields (JSON-encoded arrays)
    evidence_json: Optional[str] = None,
    risk_signals_json: Optional[str] = None,
    trigger_rule_ids_json: Optional[str] = None,
) -> AISuggestion:
    row = AISuggestion(
        record_id=record_id,
        doctor_id=doctor_id,
        section=section.value,
        content=content,
        detail=detail,
        confidence=confidence,
        urgency=urgency,
        intervention=intervention,
        is_custom=is_custom,
        cited_knowledge_ids=cited_knowledge_ids,
        prompt_hash=prompt_hash,
        evidence_json=evidence_json,
        risk_signals_json=risk_signals_json,
        trigger_rule_ids_json=trigger_rule_ids_json,
        decision=SuggestionDecision.custom.value if is_custom else None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_suggestions_for_record(
    session: AsyncSession, record_id: int
) -> List[AISuggestion]:
    stmt = (
        select(AISuggestion)
        .where(AISuggestion.record_id == record_id)
        .order_by(AISuggestion.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_suggestion_by_id(
    session: AsyncSession, suggestion_id: int
) -> Optional[AISuggestion]:
    return await session.get(AISuggestion, suggestion_id)


async def update_decision(
    session: AsyncSession,
    suggestion_id: int,
    *,
    decision: SuggestionDecision,
    edited_text: Optional[str] = None,
    reason: Optional[str] = None,
) -> Optional[AISuggestion]:
    row = await session.get(AISuggestion, suggestion_id)
    if not row:
        return None
    row.decision = decision.value
    row.edited_text = edited_text
    row.reason = reason
    row.decided_at = _utcnow()
    await session.commit()
    await session.refresh(row)
    return row


async def has_suggestions(session: AsyncSession, record_id: int) -> bool:
    stmt = (
        select(AISuggestion.id)
        .where(AISuggestion.record_id == record_id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.first() is not None
