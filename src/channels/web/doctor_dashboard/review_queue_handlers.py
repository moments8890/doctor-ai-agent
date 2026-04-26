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
        return "今天"
    if delta.days == 1:
        return "昨天"
    if delta.days < 7:
        return f"{delta.days}天前"
    if delta.days < 30:
        return f"{delta.days // 7}周前"
    if delta.days < 365:
        return f"{delta.days // 30}个月前"
    return f"{delta.days // 365}年前"


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
    seed_source: Optional[str] = Query(default=None),  # 'chat_detected' | 'explicit_intake' | None=all
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Return pending + completed AI suggestion items for the review queue page."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    # ── 1. Summary counts (pending = distinct records, not individual suggestions) ──
    pending_count_stmt = (
        select(func.count(func.distinct(AISuggestion.record_id)))
        .where(AISuggestion.doctor_id == resolved, AISuggestion.decision == None)  # noqa: E711
    )
    decided_count_stmt = (
        select(
            func.sum(case((AISuggestion.decision == "confirmed", 1), else_=0)).label("confirmed"),
            func.sum(case((AISuggestion.decision == "edited", 1), else_=0)).label("modified"),
        )
        .where(AISuggestion.doctor_id == resolved)
    )
    pending_count = (await session.execute(pending_count_stmt)).scalar() or 0
    decided = (await session.execute(decided_count_stmt)).one()
    summary = {
        "pending": pending_count,
        "confirmed": decided.confirmed,
        "modified": decided.modified,
    }

    # ── 2. Pending suggestions ─────────────────────────────────────────
    pending_stmt = (
        select(
            AISuggestion,
            MedicalRecordDB.patient_id,
            MedicalRecordDB.chief_complaint.label("chief_complaint"),
            MedicalRecordDB.record_type.label("record_type"),
            MedicalRecordDB.seed_source.label("record_seed_source"),
            MedicalRecordDB.extraction_confidence.label("record_extraction_confidence"),
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
    )
    if seed_source:
        pending_stmt = pending_stmt.where(MedicalRecordDB.seed_source == seed_source)
    pending_stmt = pending_stmt.limit(50)
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

    # Build pending items — grouped by record_id (1 card per record)
    from collections import OrderedDict
    record_groups: OrderedDict[int, dict] = OrderedDict()
    for row in pending_rows:
        sug: AISuggestion = row[0]
        rid = sug.record_id
        if rid in record_groups:
            record_groups[rid]["suggestion_count"] += 1
            # Promote urgency if any suggestion is urgent
            if sug.urgency in ("urgent", "紧急"):
                record_groups[rid]["urgency"] = "urgent"
            continue

        patient_name = row.patient_name or "未知患者"
        patient_id = row.patient_id
        chief_complaint = row.chief_complaint or ""
        record_type = row.record_type or "visit"
        rec_seed_source = row.record_seed_source
        rec_extraction_confidence = row.record_extraction_confidence

        cited_ids = pending_citations.get(sug.id, [])
        rule_cited: str | None = None
        if cited_ids:
            titles = [kb_titles[kid] for kid in cited_ids if kid in kb_titles]
            rule_cited = titles[0] if titles else None

        record_groups[rid] = {
            "id": sug.id,
            "record_id": rid,
            "suggestion_id": sug.id,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "chief_complaint": chief_complaint,
            "record_type": record_type,
            "seed_source": rec_seed_source,
            "extraction_confidence": rec_extraction_confidence,
            "time": _relative_time(sug.created_at),
            "urgency": _map_urgency_label(sug.urgency),
            "section": sug.section,
            "content": sug.content,
            "detail": sug.detail,
            "rule_cited": rule_cited,
            "suggestion_count": 1,
        }

    pending_items: list[dict] = list(record_groups.values())

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
