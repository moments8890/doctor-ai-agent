"""
专科量表评分的数据库操作。
"""
from __future__ import annotations

import json
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.scores import SpecialtyScore


async def save_specialty_scores(
    session: AsyncSession,
    record_id: int,
    doctor_id: str,
    scores: List[dict],
) -> None:
    """Persist specialty scale scores linked to a medical record.

    Each item in `scores` should have keys: score_type, score_value (optional),
    raw_text (optional), details (optional dict).
    """
    for s in scores:
        details = s.get("details")
        row = SpecialtyScore(
            record_id=record_id,
            doctor_id=doctor_id,
            score_type=s.get("score_type", "UNKNOWN"),
            score_value=s.get("score_value"),
            raw_text=(s.get("raw_text") or "")[:256],
            details_json=json.dumps(details, ensure_ascii=False) if details else None,
        )
        session.add(row)
    if scores:
        await session.flush()


async def get_scores_for_record(
    session: AsyncSession,
    record_id: int,
    doctor_id: str,
) -> List[SpecialtyScore]:
    """Return all specialty scores for a given medical record, scoped to the requesting doctor."""
    result = await session.execute(
        select(SpecialtyScore)
        .where(SpecialtyScore.record_id == record_id, SpecialtyScore.doctor_id == doctor_id)
        .order_by(SpecialtyScore.id)
    )
    return list(result.scalars().all())
