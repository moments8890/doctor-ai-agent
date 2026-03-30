"""AI activity feed & flagged-patients API for the doctor management UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from db.engine import get_db
from db.models.ai_suggestion import AISuggestion
from db.models.message_draft import MessageDraft
from db.models.patient import Patient
from db.models.patient_message import PatientMessage
from db.models.tasks import DoctorTask
from domain.knowledge.usage_tracking import get_recent_activity

router = APIRouter(tags=["ui"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _urgency_rank(urgency: str) -> int:
    """Map urgency label to a comparable integer for sorting."""
    return {"urgent": 3, "high": 2, "medium": 1, "low": 0}.get(urgency, 0)


def _safe_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


# ---------------------------------------------------------------------------
# 3B — AI Activity Feed
# ---------------------------------------------------------------------------


@router.get("/api/manage/ai/activity")
async def ai_activity_feed(
    doctor_id: str = Query(...),
    limit: int = Query(20, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Unified feed of recent AI actions: citations, diagnoses, drafts, tasks."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    events: list[dict] = []

    # 1. Recent KB citations
    citations = await get_recent_activity(session, resolved, limit=limit)
    for c in citations:
        events.append({
            "type": "citation",
            "description": f"引用了知识库条目 KB-{c['knowledge_item_id']}",
            "patient_id": c.get("patient_id"),
            "timestamp": c["created_at"],
        })

    # 2. Recent AI suggestions
    suggestions = (
        await session.execute(
            select(AISuggestion)
            .where(AISuggestion.doctor_id == resolved)
            .order_by(desc(AISuggestion.created_at))
            .limit(limit)
        )
    ).scalars().all()
    for s in suggestions:
        events.append({
            "type": "diagnosis",
            "description": f"生成诊断建议：{s.content[:30]}",
            "patient_id": None,
            "record_id": s.record_id,
            "timestamp": _safe_iso(s.created_at),
        })

    # 3. Recent drafts
    drafts = (
        await session.execute(
            select(MessageDraft)
            .where(MessageDraft.doctor_id == resolved)
            .order_by(desc(MessageDraft.created_at))
            .limit(limit)
        )
    ).scalars().all()
    for d in drafts:
        events.append({
            "type": "draft",
            "description": "起草了随访回复",
            "patient_id": d.patient_id,
            "timestamp": _safe_iso(d.created_at),
        })

    # 4. Recent auto-generated tasks
    tasks = (
        await session.execute(
            select(DoctorTask)
            .where(DoctorTask.doctor_id == resolved)
            .order_by(desc(DoctorTask.created_at))
            .limit(limit)
        )
    ).scalars().all()
    for t in tasks:
        events.append({
            "type": "task",
            "description": f"创建任务：{t.title or '待办'}",
            "patient_id": t.patient_id,
            "timestamp": _safe_iso(t.created_at),
        })

    # Merge all, sort by timestamp desc, take top N
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    trimmed = events[:limit]

    # Resolve patient names for events that have a patient_id
    raw_pids = [e["patient_id"] for e in trimmed if e.get("patient_id")]
    int_pids = []
    for p in raw_pids:
        try:
            int_pids.append(int(p))
        except (ValueError, TypeError):
            pass
    int_pids = list(set(int_pids))
    if int_pids:
        name_rows = (
            await session.execute(
                select(Patient.id, Patient.name)
                .where(Patient.id.in_(int_pids))
            )
        ).all()
        name_map = {str(pid): name for pid, name in name_rows}
        for e in trimmed:
            pid = str(e.get("patient_id", ""))
            if pid and pid in name_map:
                e["patient_name"] = name_map[pid]

    return {"activity": trimmed}


# ---------------------------------------------------------------------------
# 3C — AI-Flagged Patients
# ---------------------------------------------------------------------------


@router.get("/api/manage/patients/ai-attention")
async def ai_flagged_patients(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Surfaces patients needing doctor attention: due tasks, unread messages, unreviewed suggestions."""
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    flagged: list[dict] = []

    now = datetime.now(timezone.utc)

    # 1. Tasks due today or overdue
    due_tasks = (
        await session.execute(
            select(DoctorTask)
            .where(
                DoctorTask.doctor_id == resolved,
                DoctorTask.status == "pending",
                DoctorTask.due_at <= now,
            )
            .limit(10)
        )
    ).scalars().all()
    for t in due_tasks:
        desc_text = t.title or (t.content[:20] if t.content else "待办")
        flagged.append({
            "patient_id": t.patient_id,
            "reason": f"任务到期：{desc_text}",
            "urgency": "high",
            "type": "due_task",
        })

    # 2. Unread escalated messages (ai_handled=False → needs human review)
    unread = (
        await session.execute(
            select(PatientMessage)
            .where(
                PatientMessage.doctor_id == resolved,
                PatientMessage.direction == "inbound",
                PatientMessage.ai_handled == False,  # noqa: E712
            )
            .order_by(desc(PatientMessage.created_at))
            .limit(10)
        )
    ).scalars().all()
    for m in unread:
        urgency = "urgent" if m.triage_category in ("urgent", "emergency") else "medium"
        flagged.append({
            "patient_id": m.patient_id,
            "reason": "患者消息待处理",
            "urgency": urgency,
            "type": "unread_message",
        })

    # 3. Unreviewed AI suggestions
    unreviewed = (
        await session.execute(
            select(AISuggestion)
            .where(
                AISuggestion.doctor_id == resolved,
                AISuggestion.decision == None,  # noqa: E711
            )
            .limit(10)
        )
    ).scalars().all()
    for s in unreviewed:
        flagged.append({
            "patient_id": None,
            "record_id": s.record_id,
            "reason": f"AI建议待审核：{s.content[:20]}",
            "urgency": "medium",
            "type": "unreviewed_suggestion",
        })

    # Deduplicate by patient_id (or record_id), keep highest urgency
    seen: dict[str | int | None, dict] = {}
    for f in flagged:
        pid = f.get("patient_id") or f.get("record_id")
        if pid not in seen or _urgency_rank(f["urgency"]) > _urgency_rank(seen[pid]["urgency"]):
            seen[pid] = f

    result = sorted(seen.values(), key=lambda x: _urgency_rank(x["urgency"]), reverse=True)

    # Resolve patient names for all flagged items that have a patient_id
    patient_ids = [r["patient_id"] for r in result if r.get("patient_id")]
    if patient_ids:
        name_rows = (
            await session.execute(
                select(Patient.id, Patient.name)
                .where(Patient.id.in_(patient_ids))
            )
        ).all()
        name_map = {pid: name for pid, name in name_rows}
        for r in result:
            pid = r.get("patient_id")
            if pid and pid in name_map:
                r["patient_name"] = name_map[pid]

    return {"patients": result}
