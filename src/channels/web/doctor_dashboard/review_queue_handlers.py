"""Review queue API — pending / completed AI suggestions for the doctor management UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.ai_suggestion import AISuggestion
from db.models.doctor import DoctorKnowledgeItem
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from domain.knowledge.citation_parser import extract_citations

router = APIRouter(tags=["ui"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _relative_time(dt: datetime | None) -> str:
    """Format a datetime into Chinese relative time string.

    Examples: "今天 14:32", "昨天", "3月25日"
    """
    if dt is None:
        return ""

    now = datetime.now(timezone.utc)

    # Ensure dt is timezone-aware for comparison
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    delta = now - dt

    if delta.days == 0:
        return f"今天 {dt.strftime('%H:%M')}"
    if delta.days == 1:
        return "昨天"
    if delta.days < 365:
        return f"{dt.month}月{dt.day}日"
    return f"{dt.year}年{dt.month}月{dt.day}日"


def _map_urgency_label(urgency: str | None) -> str:
    """Map stored urgency value to the Chinese label the frontend expects."""
    if urgency in ("urgent", "紧急"):
        return "urgent"
    return "pending"


# ---------------------------------------------------------------------------
# GET /api/manage/review/queue
# ---------------------------------------------------------------------------


@router.get("/api/manage/review/queue")
async def review_queue(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return pending + completed AI suggestion items for the review queue page."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    # ── 1. Summary counts ──────────────────────────────────────────────
    count_stmt = (
        select(
            func.count().filter(AISuggestion.decision == None).label("pending"),  # noqa: E711
            func.count().filter(AISuggestion.decision == "confirmed").label("confirmed"),
            func.count().filter(AISuggestion.decision == "edited").label("modified"),
        )
        .where(AISuggestion.doctor_id == resolved)
    )
    counts = (await session.execute(count_stmt)).one()
    summary = {
        "pending": counts.pending,
        "confirmed": counts.confirmed,
        "modified": counts.modified,
    }

    # ── 2. Pending suggestions ─────────────────────────────────────────
    pending_stmt = (
        select(
            AISuggestion,
            MedicalRecordDB.patient_id,
            Patient.name.label("patient_name"),
        )
        .join(MedicalRecordDB, MedicalRecordDB.id == AISuggestion.record_id)
        .outerjoin(Patient, Patient.id == MedicalRecordDB.patient_id)
        .where(
            AISuggestion.doctor_id == resolved,
            AISuggestion.decision == None,  # noqa: E711
        )
        .order_by(
            # urgent first
            case(
                (AISuggestion.urgency == "urgent", 0),
                else_=1,
            ),
            desc(AISuggestion.created_at),
        )
        .limit(50)
    )
    pending_rows = (await session.execute(pending_stmt)).all()

    # Gather all KB citation IDs across pending suggestions for batch lookup
    all_cited_ids: set[int] = set()
    pending_citations: dict[int, list[int]] = {}  # suggestion_id → [kb_id, ...]
    for row in pending_rows:
        sug: AISuggestion = row[0]
        text = (sug.detail or "") + " " + (sug.content or "")
        result = extract_citations(text)
        pending_citations[sug.id] = result.cited_ids
        all_cited_ids.update(result.cited_ids)

    # Batch-fetch KB item titles
    kb_titles: dict[int, str] = {}
    if all_cited_ids:
        kb_stmt = (
            select(DoctorKnowledgeItem.id, DoctorKnowledgeItem.title)
            .where(
                DoctorKnowledgeItem.id.in_(all_cited_ids),
                DoctorKnowledgeItem.doctor_id == resolved,
            )
        )
        for kb_row in (await session.execute(kb_stmt)).all():
            kb_titles[kb_row.id] = kb_row.title or f"KB-{kb_row.id}"

    # Build pending items
    pending_items: list[dict] = []
    for row in pending_rows:
        sug: AISuggestion = row[0]
        patient_name = row.patient_name or "未知患者"
        patient_id = row.patient_id

        cited_ids = pending_citations.get(sug.id, [])
        # Pick first cited rule name as rule_cited string (matches frontend expectation)
        rule_cited: str | None = None
        if cited_ids:
            titles = [kb_titles[kid] for kid in cited_ids if kid in kb_titles]
            rule_cited = titles[0] if titles else None

        pending_items.append({
            "id": sug.id,
            "record_id": sug.record_id,
            "suggestion_id": sug.id,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "time": _relative_time(sug.created_at),
            "urgency": _map_urgency_label(sug.urgency),
            "section": sug.section,
            "content": sug.content,
            "detail": sug.detail,
            "rule_cited": rule_cited,
        })

    # ── 3. Completed suggestions ───────────────────────────────────────
    completed_stmt = (
        select(
            AISuggestion,
            Patient.name.label("patient_name"),
        )
        .join(MedicalRecordDB, MedicalRecordDB.id == AISuggestion.record_id)
        .outerjoin(Patient, Patient.id == MedicalRecordDB.patient_id)
        .where(
            AISuggestion.doctor_id == resolved,
            AISuggestion.decision != None,  # noqa: E711
        )
        .order_by(desc(AISuggestion.decided_at))
        .limit(20)
    )
    completed_rows = (await session.execute(completed_stmt)).all()

    # Count cited rules per completed suggestion
    completed_items: list[dict] = []
    for row in completed_rows:
        sug: AISuggestion = row[0]
        patient_name = row.patient_name or "未知患者"

        # Count citations in detail/content
        text = (sug.detail or "") + " " + (sug.content or "")
        cited = extract_citations(text)
        rule_count = len(cited.cited_ids)

        # For edited items, show edited_text snippet as detail
        detail: str | None = None
        if sug.decision == "edited" and sug.edited_text:
            detail = f"修改为：{sug.edited_text[:40]}"

        completed_items.append({
            "id": sug.id,
            "patient_name": patient_name,
            "content": sug.content[:50] if sug.content else "",
            "decision": sug.decision,
            "rule_count": rule_count,
            "detail": detail,
            "time": _relative_time(sug.decided_at),
        })

    return {
        "summary": summary,
        "pending": pending_items,
        "completed": completed_items,
    }
