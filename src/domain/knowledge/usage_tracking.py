"""Knowledge usage tracking: log citations, query stats and activity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select, update

from db.models.doctor import DoctorKnowledgeItem
from db.models.knowledge_usage import KnowledgeUsageLog
from utils.log import log


async def log_citations(
    session,
    doctor_id: str,
    cited_kb_ids: List[int],
    usage_context: str,
    patient_id: Optional[str] = None,
    record_id: Optional[int] = None,
    draft_id: Optional[int] = None,
) -> int:
    """Create a KnowledgeUsageLog entry for each cited KB ID.

    Also increments ``reference_count`` on each cited DoctorKnowledgeItem.
    Returns the count of logged entries. No-op if *cited_kb_ids* is empty.
    """
    if not cited_kb_ids:
        return 0

    count = 0
    for kb_id in cited_kb_ids:
        entry = KnowledgeUsageLog(
            doctor_id=doctor_id,
            knowledge_item_id=kb_id,
            usage_context=usage_context,
            patient_id=patient_id,
            record_id=record_id,
            draft_id=draft_id,
        )
        session.add(entry)
        count += 1

    # Increment reference_count on each cited knowledge item.
    await session.execute(
        update(DoctorKnowledgeItem)
        .where(DoctorKnowledgeItem.id.in_(cited_kb_ids))
        .values(reference_count=DoctorKnowledgeItem.reference_count + 1)
    )

    await session.commit()
    log(
        f"[KnowledgeUsage] logged {count} citation(s) doctor={doctor_id} context={usage_context}",
    )
    return count


async def get_knowledge_stats(
    session,
    doctor_id: str,
    days: int = 7,
) -> List[Dict]:
    """Query KnowledgeUsageLog grouped by knowledge_item_id.

    Filters by *doctor_id* and entries created within the last *days* days.
    Returns list of dicts sorted by total_count descending:
    ``[{"knowledge_item_id": int, "total_count": int, "last_used": str}]``
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(
            KnowledgeUsageLog.knowledge_item_id,
            func.count().label("total_count"),
            func.max(KnowledgeUsageLog.created_at).label("last_used"),
        )
        .where(KnowledgeUsageLog.doctor_id == doctor_id)
        .where(KnowledgeUsageLog.created_at >= cutoff)
        .group_by(KnowledgeUsageLog.knowledge_item_id)
        .order_by(func.count().desc())
    )

    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "knowledge_item_id": row.knowledge_item_id,
            "total_count": row.total_count,
            "last_used": row.last_used.isoformat() if row.last_used else None,
        }
        for row in rows
    ]


async def get_recent_activity(
    session,
    doctor_id: str,
    limit: int = 20,
) -> List[Dict]:
    """Query recent KnowledgeUsageLog entries for a doctor.

    Returns list of dicts ordered by created_at descending:
    ``[{"id": int, "knowledge_item_id": int, "usage_context": str,
        "patient_id": str|None, "record_id": int|None, "created_at": str}]``
    """
    stmt = (
        select(KnowledgeUsageLog)
        .where(KnowledgeUsageLog.doctor_id == doctor_id)
        .order_by(KnowledgeUsageLog.created_at.desc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "id": row.id,
            "knowledge_item_id": row.knowledge_item_id,
            "usage_context": row.usage_context,
            "patient_id": row.patient_id,
            "record_id": row.record_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
