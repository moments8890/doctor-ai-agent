"""
Admin overview API — aggregated stats and activity feeds for beta monitoring dashboard.

Endpoints:
  GET /api/admin/overview
  GET /api/admin/doctors
  GET /api/admin/activity
  GET /api/admin/doctors/{doctor_id}
  GET /api/admin/doctors/{doctor_id}/patients
  GET /api/admin/doctors/{doctor_id}/timeline
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_db
from db.models import (
    AISuggestion,
    AuditLog,
    DoctorEdit,
    DoctorPersona,
    DoctorWechat,
    InviteCode,
    KnowledgeUsageLog,
    PatientAuth,
    PersonaPendingItem,
    SuggestionDecision,
    UserPreferences,
    Doctor,
    DoctorChatLog,
    DoctorKnowledgeItem,
    DoctorTask,
    InterviewSessionDB,
    MedicalRecordDB,
    MessageDraft,
    Patient,
    PatientMessage,
    TaskStatus,
)
from channels.web.doctor_dashboard.filters import _fmt_ts, apply_exclude_test_doctors

router = APIRouter(tags=["admin-overview"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _cutoff_24h() -> datetime:
    return _now_utc() - timedelta(hours=24)


def _cutoff_days(n: int) -> datetime:
    return _now_utc() - timedelta(days=n)


# ---------------------------------------------------------------------------
# GET /api/admin/overview
# ---------------------------------------------------------------------------

@router.get("/api/admin/overview")
async def admin_overview(db: AsyncSession = Depends(get_db)) -> dict:
    """Aggregated platform metrics for a pre-launch medical AI dashboard."""
    now = _now_utc()
    cutoff_7d = _cutoff_days(7)
    cutoff_14d = _cutoff_days(14)
    cutoff_3d = _cutoff_days(3)

    def _change_pct(current: int | float, prev: int | float) -> int:
        return round(((current - prev) / max(prev, 1)) * 100)

    # -----------------------------------------------------------------------
    # HERO: active_doctors
    # -----------------------------------------------------------------------
    # Distinct doctor_ids seen in any activity table in the 7d window
    activity_tables = [
        (InterviewSessionDB, InterviewSessionDB.doctor_id, InterviewSessionDB.created_at),
        (MedicalRecordDB, MedicalRecordDB.doctor_id, MedicalRecordDB.created_at),
        (PatientMessage, PatientMessage.doctor_id, PatientMessage.created_at),
        (DoctorChatLog, DoctorChatLog.doctor_id, DoctorChatLog.created_at),
    ]

    active_ids_cur: set[str] = set()
    active_ids_prev: set[str] = set()
    for _model, did_col, ts_col in activity_tables:
        rows_cur = (
            await db.execute(
                apply_exclude_test_doctors(
                    select(func.distinct(did_col)).where(ts_col >= cutoff_7d),
                    did_col,
                )
            )
        ).scalars().all()
        active_ids_cur.update(rows_cur)

        rows_prev = (
            await db.execute(
                apply_exclude_test_doctors(
                    select(func.distinct(did_col)).where(
                        and_(ts_col >= cutoff_14d, ts_col < cutoff_7d)
                    ),
                    did_col,
                )
            )
        ).scalars().all()
        active_ids_prev.update(rows_prev)

    active_cur = len(active_ids_cur)
    active_prev = len(active_ids_prev)

    total_doctors = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(Doctor),
                Doctor.doctor_id,
            )
        )
    ).scalar() or 0

    # -----------------------------------------------------------------------
    # HERO: interviews
    # -----------------------------------------------------------------------
    interviews_started_cur = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(InterviewSessionDB).where(
                    InterviewSessionDB.created_at >= cutoff_7d
                ),
                InterviewSessionDB.doctor_id,
            )
        )
    ).scalar() or 0

    _completed_statuses = ("confirmed",)
    interviews_completed_cur = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(InterviewSessionDB).where(
                    and_(
                        InterviewSessionDB.created_at >= cutoff_7d,
                        InterviewSessionDB.status.in_(_completed_statuses),
                    )
                ),
                InterviewSessionDB.doctor_id,
            )
        )
    ).scalar() or 0

    interviews_started_prev = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(InterviewSessionDB).where(
                    and_(
                        InterviewSessionDB.created_at >= cutoff_14d,
                        InterviewSessionDB.created_at < cutoff_7d,
                    )
                ),
                InterviewSessionDB.doctor_id,
            )
        )
    ).scalar() or 0

    completion_rate = round(
        interviews_completed_cur / max(interviews_started_cur, 1), 2
    )

    # -----------------------------------------------------------------------
    # HERO: ai_acceptance
    # -----------------------------------------------------------------------
    ai_rows_cur = (
        await db.execute(
            apply_exclude_test_doctors(
                select(AISuggestion.decision, func.count().label("cnt"))
                .where(
                    and_(
                        AISuggestion.decided_at >= cutoff_7d,
                        AISuggestion.decision.isnot(None),
                    )
                )
                .group_by(AISuggestion.decision),
                AISuggestion.doctor_id,
            )
        )
    ).all()
    ai_cur: dict[str, int] = {}
    for decision, cnt in ai_rows_cur:
        ai_cur[decision] = ai_cur.get(decision, 0) + cnt

    ai_confirmed_cur = ai_cur.get(SuggestionDecision.confirmed, 0) + ai_cur.get("confirmed", 0)
    ai_edited_cur = ai_cur.get(SuggestionDecision.edited, 0) + ai_cur.get("edited", 0)
    ai_rejected_cur = ai_cur.get(SuggestionDecision.rejected, 0) + ai_cur.get("rejected", 0)
    ai_total_cur = ai_confirmed_cur + ai_edited_cur + ai_rejected_cur
    ai_rate_cur = round(ai_confirmed_cur / max(ai_total_cur, 1), 2)

    ai_rows_prev = (
        await db.execute(
            apply_exclude_test_doctors(
                select(AISuggestion.decision, func.count().label("cnt"))
                .where(
                    and_(
                        AISuggestion.decided_at >= cutoff_14d,
                        AISuggestion.decided_at < cutoff_7d,
                        AISuggestion.decision.isnot(None),
                    )
                )
                .group_by(AISuggestion.decision),
                AISuggestion.doctor_id,
            )
        )
    ).all()
    ai_prev: dict[str, int] = {}
    for decision, cnt in ai_rows_prev:
        ai_prev[decision] = ai_prev.get(decision, 0) + cnt

    ai_confirmed_prev = ai_prev.get(SuggestionDecision.confirmed, 0) + ai_prev.get("confirmed", 0)
    ai_edited_prev = ai_prev.get(SuggestionDecision.edited, 0) + ai_prev.get("edited", 0)
    ai_rejected_prev = ai_prev.get(SuggestionDecision.rejected, 0) + ai_prev.get("rejected", 0)
    ai_total_prev = ai_confirmed_prev + ai_edited_prev + ai_rejected_prev
    ai_rate_prev = round(ai_confirmed_prev / max(ai_total_prev, 1), 2)

    # -----------------------------------------------------------------------
    # HERO: unanswered_messages
    # -----------------------------------------------------------------------
    # Inbound messages with no subsequent outbound for the same patient
    latest_outbound = (
        select(
            PatientMessage.patient_id,
            func.max(PatientMessage.created_at).label("last_out"),
        )
        .where(PatientMessage.direction == "outbound")
        .group_by(PatientMessage.patient_id)
        .subquery()
    )

    unanswered_rows = (
        await db.execute(
            apply_exclude_test_doctors(
                select(PatientMessage.created_at)
                .outerjoin(
                    latest_outbound,
                    PatientMessage.patient_id == latest_outbound.c.patient_id,
                )
                .where(
                    and_(
                        PatientMessage.direction == "inbound",
                        # No outbound at all, or last outbound before this inbound
                        (latest_outbound.c.last_out.is_(None))
                        | (PatientMessage.created_at > latest_outbound.c.last_out),
                    )
                )
                .order_by(PatientMessage.created_at.asc()),
                PatientMessage.doctor_id,
            )
        )
    ).scalars().all()

    unanswered_count = len(unanswered_rows)
    if unanswered_rows:
        oldest_ts = unanswered_rows[0]
        if oldest_ts and oldest_ts.tzinfo is None:
            oldest_ts = oldest_ts.replace(tzinfo=timezone.utc)
        oldest_hours = round(
            (now - oldest_ts).total_seconds() / 3600, 1
        ) if oldest_ts else 0.0
    else:
        oldest_hours = 0.0

    # -----------------------------------------------------------------------
    # HERO: system_health (24h window, from llm_calls.jsonl)
    # -----------------------------------------------------------------------
    cutoff_24h_iso = (_now_utc() - timedelta(hours=24)).isoformat()
    llm_total = 0
    llm_errors = 0
    latencies: list[float] = []
    try:
        import json as _json

        llm_log = Path(__file__).resolve().parents[4] / "logs" / "llm_calls.jsonl"
        if llm_log.exists():
            with open(llm_log, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = _json.loads(line)
                        if entry.get("timestamp", "") >= cutoff_24h_iso:
                            llm_total += 1
                            if entry.get("status") == "error":
                                llm_errors += 1
                            lat = entry.get("latency_ms")
                            if lat is not None:
                                latencies.append(float(lat))
                    except (ValueError, _json.JSONDecodeError):
                        pass
    except OSError:
        pass

    latencies.sort()
    p95_latency = (
        latencies[int(len(latencies) * 0.95)] if latencies else 0
    )
    error_rate = round(llm_errors / max(llm_total, 1), 3)

    # -----------------------------------------------------------------------
    # SECONDARY: new_records
    # -----------------------------------------------------------------------
    records_cur = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(MedicalRecordDB).where(
                    MedicalRecordDB.created_at >= cutoff_7d
                ),
                MedicalRecordDB.doctor_id,
            )
        )
    ).scalar() or 0
    records_prev = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(MedicalRecordDB).where(
                    and_(
                        MedicalRecordDB.created_at >= cutoff_14d,
                        MedicalRecordDB.created_at < cutoff_7d,
                    )
                ),
                MedicalRecordDB.doctor_id,
            )
        )
    ).scalar() or 0

    # SECONDARY: ai_replies (outbound messages)
    ai_replies_cur = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(PatientMessage).where(
                    and_(
                        PatientMessage.direction == "outbound",
                        PatientMessage.created_at >= cutoff_7d,
                    )
                ),
                PatientMessage.doctor_id,
            )
        )
    ).scalar() or 0
    ai_replies_prev = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(PatientMessage).where(
                    and_(
                        PatientMessage.direction == "outbound",
                        PatientMessage.created_at >= cutoff_14d,
                        PatientMessage.created_at < cutoff_7d,
                    )
                ),
                PatientMessage.doctor_id,
            )
        )
    ).scalar() or 0

    # SECONDARY: patient_messages (inbound)
    patient_msgs_cur = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(PatientMessage).where(
                    and_(
                        PatientMessage.direction == "inbound",
                        PatientMessage.created_at >= cutoff_7d,
                    )
                ),
                PatientMessage.doctor_id,
            )
        )
    ).scalar() or 0
    patient_msgs_prev = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(PatientMessage).where(
                    and_(
                        PatientMessage.direction == "inbound",
                        PatientMessage.created_at >= cutoff_14d,
                        PatientMessage.created_at < cutoff_7d,
                    )
                ),
                PatientMessage.doctor_id,
            )
        )
    ).scalar() or 0

    # SECONDARY: new_patients
    patients_cur = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(Patient).where(
                    Patient.created_at >= cutoff_7d
                ),
                Patient.doctor_id,
            )
        )
    ).scalar() or 0
    patients_prev = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(Patient).where(
                    and_(
                        Patient.created_at >= cutoff_14d,
                        Patient.created_at < cutoff_7d,
                    )
                ),
                Patient.doctor_id,
            )
        )
    ).scalar() or 0

    # SECONDARY: new_knowledge
    kb_cur = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(DoctorKnowledgeItem).where(
                    DoctorKnowledgeItem.created_at >= cutoff_7d
                ),
                DoctorKnowledgeItem.doctor_id,
            )
        )
    ).scalar() or 0
    kb_prev = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(DoctorKnowledgeItem).where(
                    and_(
                        DoctorKnowledgeItem.created_at >= cutoff_14d,
                        DoctorKnowledgeItem.created_at < cutoff_7d,
                    )
                ),
                DoctorKnowledgeItem.doctor_id,
            )
        )
    ).scalar() or 0

    # SECONDARY: avg_interview_turns (completed interviews in 7d)
    avg_turns_row = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.avg(InterviewSessionDB.turn_count))
                .where(
                    and_(
                        InterviewSessionDB.created_at >= cutoff_7d,
                        InterviewSessionDB.status.in_(_completed_statuses),
                    )
                ),
                InterviewSessionDB.doctor_id,
            )
        )
    ).scalar()
    avg_interview_turns = round(float(avg_turns_row), 1) if avg_turns_row else 0.0

    # SECONDARY: overdue_tasks
    overdue_count = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(DoctorTask).where(
                    and_(
                        DoctorTask.status == TaskStatus.pending,
                        DoctorTask.due_at != None,  # noqa: E711
                        DoctorTask.due_at < now,
                    )
                ),
                DoctorTask.doctor_id,
            )
        )
    ).scalar() or 0

    # SECONDARY: response_gap_p50_hours
    # For each inbound message in 7d that got a reply, compute time to first
    # subsequent outbound for the same patient.
    inbound_7d = (
        await db.execute(
            apply_exclude_test_doctors(
                select(PatientMessage)
                .where(
                    and_(
                        PatientMessage.direction == "inbound",
                        PatientMessage.created_at >= cutoff_7d,
                    )
                )
                .order_by(PatientMessage.created_at.asc()),
                PatientMessage.doctor_id,
            )
        )
    ).scalars().all()

    response_gaps: list[float] = []
    for msg in inbound_7d:
        first_reply = (
            await db.execute(
                select(PatientMessage.created_at)
                .where(
                    and_(
                        PatientMessage.patient_id == msg.patient_id,
                        PatientMessage.direction == "outbound",
                        PatientMessage.created_at > msg.created_at,
                    )
                )
                .order_by(PatientMessage.created_at.asc())
                .limit(1)
            )
        ).scalar()
        if first_reply:
            in_ts = msg.created_at
            out_ts = first_reply
            if in_ts and in_ts.tzinfo is None:
                in_ts = in_ts.replace(tzinfo=timezone.utc)
            if out_ts and out_ts.tzinfo is None:
                out_ts = out_ts.replace(tzinfo=timezone.utc)
            gap_hours = (out_ts - in_ts).total_seconds() / 3600
            response_gaps.append(gap_hours)

    response_gaps.sort()
    response_gap_p50 = (
        round(response_gaps[len(response_gaps) // 2], 1) if response_gaps else 0.0
    )

    # -----------------------------------------------------------------------
    # ALERTS (same format as before)
    # -----------------------------------------------------------------------
    overdue_tasks_rows = (
        await db.execute(
            apply_exclude_test_doctors(
                select(DoctorTask).where(
                    and_(
                        DoctorTask.status == TaskStatus.pending,
                        DoctorTask.due_at != None,  # noqa: E711
                        DoctorTask.due_at < now,
                    )
                ).order_by(DoctorTask.due_at.asc()).limit(10),
                DoctorTask.doctor_id,
            )
        )
    ).scalars().all()

    overdue_alerts = [
        {
            "level": "error",
            "label": "逾期任务",
            "detail": f"{t.doctor_id} → {t.title or '未命名'} 逾期",
        }
        for t in overdue_tasks_rows
    ]

    inactive_doctors_rows = (
        await db.execute(
            apply_exclude_test_doctors(
                select(Doctor).where(
                    Doctor.updated_at < cutoff_3d
                ).order_by(Doctor.updated_at.asc()).limit(10),
                Doctor.doctor_id,
            )
        )
    ).scalars().all()

    inactive_alerts = [
        {
            "level": "warn",
            "label": "不活跃",
            "detail": f"{d.name or d.doctor_id} 超过3天未登录",
        }
        for d in inactive_doctors_rows
    ]

    # -----------------------------------------------------------------------
    # Assemble response
    # -----------------------------------------------------------------------
    return {
        "hero": {
            "active_doctors": {
                "current": active_cur,
                "total": total_doctors,
                "prev": active_prev,
                "change_pct": _change_pct(active_cur, active_prev),
            },
            "interviews": {
                "started": interviews_started_cur,
                "completed": interviews_completed_cur,
                "completion_rate": completion_rate,
                "prev_started": interviews_started_prev,
                "change_pct": _change_pct(interviews_started_cur, interviews_started_prev),
            },
            "ai_acceptance": {
                "confirmed": ai_confirmed_cur,
                "edited": ai_edited_cur,
                "rejected": ai_rejected_cur,
                "rate": ai_rate_cur,
                "prev_rate": ai_rate_prev,
                "change_pct": _change_pct(ai_rate_cur * 100, ai_rate_prev * 100),
            },
            "unanswered_messages": {
                "count": unanswered_count,
                "oldest_hours": oldest_hours,
            },
            "system_health": {
                "error_rate": error_rate,
                "p95_latency_ms": p95_latency,
                "calls_24h": llm_total,
                "errors_24h": llm_errors,
            },
        },
        "secondary": {
            "new_records": {
                "current": records_cur,
                "prev": records_prev,
                "change_pct": _change_pct(records_cur, records_prev),
            },
            "ai_replies": {
                "current": ai_replies_cur,
                "prev": ai_replies_prev,
                "change_pct": _change_pct(ai_replies_cur, ai_replies_prev),
            },
            "patient_messages": {
                "current": patient_msgs_cur,
                "prev": patient_msgs_prev,
                "change_pct": _change_pct(patient_msgs_cur, patient_msgs_prev),
            },
            "new_patients": {
                "current": patients_cur,
                "prev": patients_prev,
                "change_pct": _change_pct(patients_cur, patients_prev),
            },
            "new_knowledge": {
                "current": kb_cur,
                "prev": kb_prev,
                "change_pct": _change_pct(kb_cur, kb_prev),
            },
            "avg_interview_turns": avg_interview_turns,
            "overdue_tasks": overdue_count,
            "response_gap_p50_hours": response_gap_p50,
        },
        "alerts": overdue_alerts + inactive_alerts,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/doctors
# ---------------------------------------------------------------------------

@router.get("/api/admin/doctors")
async def admin_doctors_list(db: AsyncSession = Depends(get_db)) -> dict:
    """Doctor list with per-doctor activity metrics."""
    cutoff_24h = _cutoff_24h()

    doctors = (
        await db.execute(
            apply_exclude_test_doctors(
                select(Doctor).order_by(Doctor.updated_at.desc()),
                Doctor.doctor_id,
            )
        )
    ).scalars().all()

    items: List[dict] = []
    for doc in doctors:
        did = doc.doctor_id

        patient_count = (
            await db.execute(
                select(func.count()).select_from(Patient).where(Patient.doctor_id == did)
            )
        ).scalar() or 0

        msg_today = (
            await db.execute(
                select(func.count()).select_from(PatientMessage).where(
                    and_(
                        PatientMessage.doctor_id == did,
                        PatientMessage.created_at >= cutoff_24h,
                    )
                )
            )
        ).scalar() or 0

        # AI adoption: suggestions with a decision / total suggestions
        total_suggestions = (
            await db.execute(
                select(func.count()).select_from(AISuggestion).where(
                    AISuggestion.doctor_id == did
                )
            )
        ).scalar() or 0

        decided_suggestions = (
            await db.execute(
                select(func.count()).select_from(AISuggestion).where(
                    and_(
                        AISuggestion.doctor_id == did,
                        AISuggestion.decision != None,  # noqa: E711
                    )
                )
            )
        ).scalar() or 0

        ai_adoption = (
            round(decided_suggestions / total_suggestions, 2)
            if total_suggestions > 0
            else 0.0
        )

        pending_tasks = (
            await db.execute(
                select(func.count()).select_from(DoctorTask).where(
                    and_(
                        DoctorTask.doctor_id == did,
                        DoctorTask.status == TaskStatus.pending,
                    )
                )
            )
        ).scalar() or 0

        kb_count = (
            await db.execute(
                select(func.count()).select_from(DoctorKnowledgeItem).where(
                    DoctorKnowledgeItem.doctor_id == did
                )
            )
        ).scalar() or 0

        items.append(
            {
                "doctor_id": did,
                "name": doc.name,
                "department": doc.department or "",
                "specialty": doc.specialty or "",
                "patient_count": patient_count,
                "msg_today": msg_today,
                "ai_adoption": ai_adoption,
                "pending_tasks": pending_tasks,
                "kb_count": kb_count,
                "last_active": _fmt_ts(doc.updated_at),
                "created_at": _fmt_ts(doc.created_at),
            }
        )

    return {"items": items}


# ---------------------------------------------------------------------------
# GET /api/admin/activity
# ---------------------------------------------------------------------------

@router.get("/api/admin/activity")
async def admin_activity(db: AsyncSession = Depends(get_db)) -> dict:
    """Recent activity feed: AI suggestions, records, tasks from last 24h, sorted desc."""
    cutoff_24h = _cutoff_24h()

    # AI suggestions
    suggestions = (
        await db.execute(
            apply_exclude_test_doctors(
                select(AISuggestion).where(
                    AISuggestion.created_at >= cutoff_24h
                ).order_by(AISuggestion.created_at.desc()).limit(50),
                AISuggestion.doctor_id,
            )
        )
    ).scalars().all()

    # Medical records
    records = (
        await db.execute(
            apply_exclude_test_doctors(
                select(MedicalRecordDB).where(
                    MedicalRecordDB.created_at >= cutoff_24h
                ).order_by(MedicalRecordDB.created_at.desc()).limit(50),
                MedicalRecordDB.doctor_id,
            )
        )
    ).scalars().all()

    # Tasks
    tasks = (
        await db.execute(
            apply_exclude_test_doctors(
                select(DoctorTask).where(
                    DoctorTask.created_at >= cutoff_24h
                ).order_by(DoctorTask.created_at.desc()).limit(50),
                DoctorTask.doctor_id,
            )
        )
    ).scalars().all()

    feed: List[dict] = []

    for s in suggestions:
        feed.append(
            {
                "type": "ai_suggestion",
                "id": s.id,
                "doctor_id": s.doctor_id,
                "record_id": s.record_id,
                "section": s.section,
                "decision": s.decision,
                "ts": _fmt_ts(s.created_at),
                "created_at": s.created_at,
            }
        )

    for r in records:
        feed.append(
            {
                "type": "record",
                "id": r.id,
                "doctor_id": r.doctor_id,
                "patient_id": r.patient_id,
                "record_type": r.record_type or "visit",
                "ts": _fmt_ts(r.created_at),
                "created_at": r.created_at,
            }
        )

    for t in tasks:
        feed.append(
            {
                "type": "task",
                "id": t.id,
                "doctor_id": t.doctor_id,
                "patient_id": t.patient_id,
                "title": t.title,
                "status": t.status,
                "ts": _fmt_ts(t.created_at),
                "created_at": t.created_at,
            }
        )

    # Sort merged feed by created_at desc
    feed.sort(key=lambda x: x["created_at"] or datetime.min, reverse=True)

    # Map to frontend-expected field names
    mapped: List[dict] = []
    for item in feed[:100]:
        evt_type = item["type"]
        detail = item.get("title") or item.get("section") or item.get("record_type") or ""
        mapped.append({
            "created_at": _fmt_ts(item["created_at"]),
            "doctor_id": item.get("doctor_id", ""),
            "event_type": evt_type,
            "detail": detail,
            "status": str(item.get("status") or item.get("decision") or ""),
            "patient_id": item.get("patient_id", ""),
            "id": item.get("id"),
        })

    return {"items": mapped}


# ---------------------------------------------------------------------------
# GET /api/admin/doctors/{doctor_id}
# ---------------------------------------------------------------------------

@router.get("/api/admin/doctors/{doctor_id}")
async def admin_doctor_detail(
    doctor_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """Doctor profile, setup checklist, and 7-day stats."""
    doc = (
        await db.execute(select(Doctor).where(Doctor.doctor_id == doctor_id))
    ).scalars().first()

    if not doc:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Setup checklist
    has_kb = bool(
        (
            await db.execute(
                select(func.count()).select_from(DoctorKnowledgeItem).where(
                    DoctorKnowledgeItem.doctor_id == doctor_id
                )
            )
        ).scalar() or 0
    )

    has_patients = bool(
        (
            await db.execute(
                select(func.count()).select_from(Patient).where(
                    Patient.doctor_id == doctor_id
                )
            )
        ).scalar() or 0
    )

    has_records = bool(
        (
            await db.execute(
                select(func.count()).select_from(MedicalRecordDB).where(
                    MedicalRecordDB.doctor_id == doctor_id
                )
            )
        ).scalar() or 0
    )

    has_ai_usage = bool(
        (
            await db.execute(
                select(func.count()).select_from(AISuggestion).where(
                    AISuggestion.doctor_id == doctor_id
                )
            )
        ).scalar() or 0
    )

    # 7-day daily stats
    cutoff_7d = _cutoff_days(7)
    msgs_7d = (
        await db.execute(
            select(func.count()).select_from(PatientMessage).where(
                and_(
                    PatientMessage.doctor_id == doctor_id,
                    PatientMessage.created_at >= cutoff_7d,
                )
            )
        )
    ).scalar() or 0

    records_7d = (
        await db.execute(
            select(func.count()).select_from(MedicalRecordDB).where(
                and_(
                    MedicalRecordDB.doctor_id == doctor_id,
                    MedicalRecordDB.created_at >= cutoff_7d,
                )
            )
        )
    ).scalar() or 0

    tasks_7d = (
        await db.execute(
            select(func.count()).select_from(DoctorTask).where(
                and_(
                    DoctorTask.doctor_id == doctor_id,
                    DoctorTask.created_at >= cutoff_7d,
                )
            )
        )
    ).scalar() or 0

    ai_7d = (
        await db.execute(
            select(func.count()).select_from(AISuggestion).where(
                and_(
                    AISuggestion.doctor_id == doctor_id,
                    AISuggestion.created_at >= cutoff_7d,
                )
            )
        )
    ).scalar() or 0

    # Patient count
    patient_count = (
        await db.execute(
            select(func.count()).select_from(Patient).where(
                Patient.doctor_id == doctor_id
            )
        )
    ).scalar() or 0

    # AI adoption rate (all time)
    decided_rows = (
        await db.execute(
            select(AISuggestion.decision).where(and_(
                AISuggestion.doctor_id == doctor_id,
                AISuggestion.decision.isnot(None),
            ))
        )
    ).scalars().all()
    decided_total = len(decided_rows)
    confirmed_count = sum(1 for d in decided_rows if d == SuggestionDecision.confirmed)
    edited_count = sum(1 for d in decided_rows if d == SuggestionDecision.edited)
    rejected_count = sum(1 for d in decided_rows if d == SuggestionDecision.rejected)
    ai_adoption = round(confirmed_count / decided_total, 2) if decided_total else None

    # Task completion
    tasks_completed = (
        await db.execute(
            select(func.count()).select_from(DoctorTask).where(and_(
                DoctorTask.doctor_id == doctor_id,
                DoctorTask.status == TaskStatus.completed,
            ))
        )
    ).scalar() or 0
    tasks_all = (
        await db.execute(
            select(func.count()).select_from(DoctorTask).where(
                DoctorTask.doctor_id == doctor_id,
            )
        )
    ).scalar() or 0

    # KB count
    kb_count = (
        await db.execute(
            select(func.count()).select_from(DoctorKnowledgeItem).where(
                DoctorKnowledgeItem.doctor_id == doctor_id
            )
        )
    ).scalar() or 0

    return {
        "profile": {
            "doctor_id": doc.doctor_id,
            "name": doc.name,
            "department": doc.department or "",
            "specialty": doc.specialty or "",
            "clinic_name": doc.clinic_name or "",
            "created_at": _fmt_ts(doc.created_at),
            "last_active": _fmt_ts(doc.updated_at),
        },
        "setup": {
            "has_kb": has_kb,
            "kb_count": kb_count,
            "has_patients": has_patients,
            "has_records": has_records,
            "has_ai_usage": has_ai_usage,
        },
        "stats_7d": {
            "patients": patient_count,
            "messages": msgs_7d,
            "records": records_7d,
            "tasks": tasks_7d,
            "ai_suggestions": ai_7d,
            "ai_adoption": ai_adoption,
            "ai_accepted": confirmed_count,
            "ai_edited": edited_count,
            "ai_rejected": rejected_count,
            "tasks_done": tasks_completed,
            "tasks_total": tasks_all,
        },
    }


# ---------------------------------------------------------------------------
# GET /api/admin/doctors/{doctor_id}/patients
# ---------------------------------------------------------------------------

@router.get("/api/admin/doctors/{doctor_id}/patients")
async def admin_doctor_patients(
    doctor_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """Patient list for a doctor with message/record/task counts."""
    patients = (
        await db.execute(
            select(Patient)
            .where(Patient.doctor_id == doctor_id)
            .order_by(Patient.created_at.desc())
        )
    ).scalars().all()

    items: List[dict] = []
    for p in patients:
        pid = p.id

        msg_count = (
            await db.execute(
                select(func.count()).select_from(PatientMessage).where(
                    PatientMessage.patient_id == pid
                )
            )
        ).scalar() or 0

        rec_count = (
            await db.execute(
                select(func.count()).select_from(MedicalRecordDB).where(
                    MedicalRecordDB.patient_id == pid
                )
            )
        ).scalar() or 0

        pending_tasks = (
            await db.execute(
                select(func.count()).select_from(DoctorTask).where(
                    and_(
                        DoctorTask.patient_id == pid,
                        DoctorTask.status == TaskStatus.pending,
                    )
                )
            )
        ).scalar() or 0

        # Latest inbound message
        last_msg_row = (
            await db.execute(
                select(PatientMessage)
                .where(
                    and_(
                        PatientMessage.patient_id == pid,
                        PatientMessage.direction == "inbound",
                    )
                )
                .order_by(PatientMessage.created_at.desc())
                .limit(1)
            )
        ).scalars().first()

        items.append(
            {
                "patient_id": pid,
                "name": p.name,
                "gender": p.gender,
                "year_of_birth": p.year_of_birth,
                "msg_count": msg_count,
                "rec_count": rec_count,
                "pending_tasks": pending_tasks,
                "last_message": _fmt_ts(last_msg_row.created_at) if last_msg_row else None,
            }
        )

    return {"doctor_id": doctor_id, "items": items}


# ---------------------------------------------------------------------------
# GET /api/admin/doctors/{doctor_id}/timeline
# ---------------------------------------------------------------------------

@router.get("/api/admin/doctors/{doctor_id}/timeline")
async def admin_doctor_timeline(
    doctor_id: str,
    patient_id: int = Query(..., description="Patient ID to show timeline for"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Chronological case timeline for a patient: messages, records, AI suggestions, tasks."""
    # Messages
    messages = (
        await db.execute(
            select(PatientMessage).where(
                and_(
                    PatientMessage.doctor_id == doctor_id,
                    PatientMessage.patient_id == patient_id,
                )
            ).order_by(PatientMessage.created_at.asc())
        )
    ).scalars().all()

    # Records
    records = (
        await db.execute(
            select(MedicalRecordDB).where(
                and_(
                    MedicalRecordDB.doctor_id == doctor_id,
                    MedicalRecordDB.patient_id == patient_id,
                )
            ).order_by(MedicalRecordDB.created_at.asc())
        )
    ).scalars().all()

    # AI suggestions linked to those records
    record_ids = [r.id for r in records]
    suggestions: List = []
    if record_ids:
        suggestions = (
            await db.execute(
                select(AISuggestion).where(
                    and_(
                        AISuggestion.doctor_id == doctor_id,
                        AISuggestion.record_id.in_(record_ids),
                    )
                ).order_by(AISuggestion.created_at.asc())
            )
        ).scalars().all()

    # Tasks
    tasks = (
        await db.execute(
            select(DoctorTask).where(
                and_(
                    DoctorTask.doctor_id == doctor_id,
                    DoctorTask.patient_id == patient_id,
                )
            ).order_by(DoctorTask.created_at.asc())
        )
    ).scalars().all()

    feed: List[dict] = []

    for m in messages:
        feed.append(
            {
                "type": "message",
                "id": m.id,
                "direction": m.direction,
                "content": m.content,
                "ts": _fmt_ts(m.created_at),
                "created_at": m.created_at,
            }
        )

    for r in records:
        feed.append(
            {
                "type": "record",
                "id": r.id,
                "record_type": r.record_type or "visit",
                "content": r.content,
                "ts": _fmt_ts(r.created_at),
                "created_at": r.created_at,
            }
        )

    for s in suggestions:
        feed.append(
            {
                "type": "ai_suggestion",
                "id": s.id,
                "record_id": s.record_id,
                "section": s.section,
                "content": s.content,
                "decision": s.decision,
                "ts": _fmt_ts(s.created_at),
                "created_at": s.created_at,
            }
        )

    for t in tasks:
        feed.append(
            {
                "type": "task",
                "id": t.id,
                "title": t.title,
                "status": t.status,
                "due_at": _fmt_ts(t.due_at),
                "ts": _fmt_ts(t.created_at),
                "created_at": t.created_at,
            }
        )

    feed.sort(key=lambda x: x["created_at"] or datetime.min)

    # Map to frontend field names
    mapped: List[dict] = []
    for item in feed:
        detail = item.get("title") or item.get("content") or item.get("section") or item.get("record_type") or ""
        mapped.append({
            "time": _fmt_ts(item["created_at"]),
            "type": item["type"],
            "detail": str(detail)[:200],
            "status": str(item.get("status") or item.get("decision") or ""),
            "id": item.get("id"),
        })

    return {
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "items": mapped,
    }


# ---------------------------------------------------------------------------
# GET /api/admin/doctors/{doctor_id}/related
# ---------------------------------------------------------------------------

@router.get("/api/admin/doctors/{doctor_id}/related")
async def admin_doctor_related(
    doctor_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """All related data for a doctor across every table."""
    LIMIT = 50

    doctor = (
        await db.execute(select(Doctor).where(Doctor.doctor_id == doctor_id))
    ).scalars().first()
    if not doctor:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Doctor not found")

    profile = {
        "doctor_id": doctor.doctor_id, "name": doctor.name,
        "specialty": doctor.specialty, "department": doctor.department,
        "phone": doctor.phone, "clinic_name": doctor.clinic_name,
        "bio": doctor.bio, "finished_onboarding": doctor.finished_onboarding,
        "created_at": _fmt_ts(doctor.created_at),
        "updated_at": _fmt_ts(doctor.updated_at),
    }

    # Patients
    patients = (await db.execute(
        select(Patient).where(Patient.doctor_id == doctor_id)
        .order_by(Patient.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    patients_data = [
        {"id": p.id, "name": p.name, "gender": p.gender,
         "year_of_birth": p.year_of_birth, "phone": p.phone or "",
         "created_at": _fmt_ts(p.created_at),
         "last_activity_at": _fmt_ts(p.last_activity_at)}
        for p in patients
    ]

    # Medical records
    records = (await db.execute(
        select(MedicalRecordDB, Patient.name.label("patient_name"))
        .outerjoin(Patient, MedicalRecordDB.patient_id == Patient.id)
        .where(MedicalRecordDB.doctor_id == doctor_id)
        .order_by(MedicalRecordDB.created_at.desc()).limit(LIMIT)
    )).all()
    records_data = [
        {"id": r.id, "patient_id": r.patient_id, "patient_name": pn,
         "record_type": r.record_type, "content": (r.content or "")[:200],
         "status": r.status, "created_at": _fmt_ts(r.created_at)}
        for r, pn in records
    ]

    # Tasks
    tasks = (await db.execute(
        select(DoctorTask, Patient.name.label("patient_name"))
        .outerjoin(Patient, DoctorTask.patient_id == Patient.id)
        .where(DoctorTask.doctor_id == doctor_id)
        .order_by(DoctorTask.created_at.desc()).limit(LIMIT)
    )).all()
    tasks_data = [
        {"id": t.id, "patient_id": t.patient_id, "patient_name": pn,
         "task_type": t.task_type, "title": t.title, "status": t.status,
         "due_at": _fmt_ts(t.due_at), "created_at": _fmt_ts(t.created_at)}
        for t, pn in tasks
    ]

    # Knowledge items
    kb = (await db.execute(
        select(DoctorKnowledgeItem).where(DoctorKnowledgeItem.doctor_id == doctor_id)
        .order_by(DoctorKnowledgeItem.updated_at.desc()).limit(LIMIT)
    )).scalars().all()
    kb_data = [
        {"id": k.id, "title": k.title, "category": k.category,
         "content": (k.content or "")[:200], "reference_count": k.reference_count,
         "created_at": _fmt_ts(k.created_at)}
        for k in kb
    ]

    # Chat log
    chats = (await db.execute(
        select(DoctorChatLog).where(DoctorChatLog.doctor_id == doctor_id)
        .order_by(DoctorChatLog.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    chats_data = [
        {"id": c.id, "session_id": c.session_id, "role": c.role,
         "content": (c.content or "")[:200], "created_at": _fmt_ts(c.created_at)}
        for c in chats
    ]

    # Interview sessions
    interviews = (await db.execute(
        select(InterviewSessionDB).where(InterviewSessionDB.doctor_id == doctor_id)
        .order_by(InterviewSessionDB.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    interviews_data = [
        {"id": s.id[:8], "patient_id": s.patient_id, "status": s.status,
         "turn_count": s.turn_count, "created_at": _fmt_ts(s.created_at)}
        for s in interviews
    ]

    # AI suggestions (across all records for this doctor)
    suggestions = (await db.execute(
        select(AISuggestion).where(AISuggestion.doctor_id == doctor_id)
        .order_by(AISuggestion.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    suggestions_data = [
        {"id": s.id, "record_id": s.record_id, "section": s.section,
         "content": (s.content or "")[:200], "decision": s.decision,
         "created_at": _fmt_ts(s.created_at)}
        for s in suggestions
    ]

    # Message drafts
    drafts = (await db.execute(
        select(MessageDraft).where(MessageDraft.doctor_id == doctor_id)
        .order_by(MessageDraft.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    drafts_data = [
        {"id": d.id, "patient_id": d.patient_id, "status": d.status,
         "draft_text": (d.draft_text or "")[:200],
         "created_at": _fmt_ts(d.created_at)}
        for d in drafts
    ]

    # Patient messages (all for this doctor)
    messages = (await db.execute(
        select(PatientMessage, Patient.name.label("patient_name"))
        .outerjoin(Patient, PatientMessage.patient_id == Patient.id)
        .where(PatientMessage.doctor_id == doctor_id)
        .order_by(PatientMessage.created_at.desc()).limit(LIMIT)
    )).all()
    messages_data = [
        {"id": m.id, "patient_id": m.patient_id, "patient_name": pn,
         "direction": m.direction, "content": (m.content or "")[:200],
         "source": m.source, "created_at": _fmt_ts(m.created_at)}
        for m, pn in messages
    ]

    # Persona
    persona = (await db.execute(
        select(DoctorPersona).where(DoctorPersona.doctor_id == doctor_id)
    )).scalars().first()
    persona_data = None
    if persona:
        import json
        persona_data = {
            "doctor_id": persona.doctor_id, "status": persona.status,
            "onboarded": persona.onboarded, "edit_count": persona.edit_count,
            "version": persona.version,
            "summary_text": (persona.summary_text or "")[:300],
            "fields": persona.fields,
            "created_at": _fmt_ts(persona.created_at),
            "updated_at": _fmt_ts(persona.updated_at),
        }

    # User preferences
    prefs = (await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == doctor_id)
    )).scalars().first()
    prefs_data = None
    if prefs:
        import json as _json
        try:
            prefs_data = {
                "user_id": prefs.user_id,
                "preferences": _json.loads(prefs.preferences_json) if prefs.preferences_json else {},
                "updated_at": _fmt_ts(prefs.updated_at),
            }
        except Exception:
            prefs_data = {"user_id": prefs.user_id, "preferences": prefs.preferences_json, "updated_at": _fmt_ts(prefs.updated_at)}

    # Doctor edits
    edits = (await db.execute(
        select(DoctorEdit).where(DoctorEdit.doctor_id == doctor_id)
        .order_by(DoctorEdit.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    edits_data = [
        {"id": e.id, "entity_type": e.entity_type, "entity_id": e.entity_id,
         "field_name": e.field_name,
         "original_text": (e.original_text or "")[:100],
         "edited_text": (e.edited_text or "")[:100],
         "rule_created": e.rule_created,
         "created_at": _fmt_ts(e.created_at)}
        for e in edits
    ]

    # Knowledge usage log
    kb_usage = (await db.execute(
        select(KnowledgeUsageLog).where(KnowledgeUsageLog.doctor_id == doctor_id)
        .order_by(KnowledgeUsageLog.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    kb_usage_data = [
        {"id": u.id, "knowledge_item_id": u.knowledge_item_id,
         "usage_context": u.usage_context, "patient_id": u.patient_id,
         "record_id": u.record_id, "created_at": _fmt_ts(u.created_at)}
        for u in kb_usage
    ]

    # WeChat binding
    wechat = (await db.execute(
        select(DoctorWechat).where(DoctorWechat.doctor_id == doctor_id)
    )).scalars().first()
    wechat_data = None
    if wechat:
        wechat_data = {
            "doctor_id": wechat.doctor_id,
            "wechat_user_id": wechat.wechat_user_id,
            "mini_openid": wechat.mini_openid,
            "created_at": _fmt_ts(wechat.created_at),
        }

    # Invite codes
    invites = (await db.execute(
        select(InviteCode).where(InviteCode.doctor_id == doctor_id)
    )).scalars().all()
    invites_data = [
        {"code": ic.code, "active": ic.active, "used_count": ic.used_count,
         "created_at": _fmt_ts(ic.created_at)}
        for ic in invites
    ]

    # Audit log
    audits = (await db.execute(
        select(AuditLog).where(AuditLog.doctor_id == doctor_id)
        .order_by(AuditLog.ts.desc()).limit(LIMIT)
    )).scalars().all()
    audits_data = [
        {"id": a.id, "action": a.action, "resource_type": a.resource_type,
         "resource_id": a.resource_id, "ok": a.ok, "ip": a.ip,
         "ts": _fmt_ts(a.ts)}
        for a in audits
    ]

    # Persona pending items
    pending_persona = (await db.execute(
        select(PersonaPendingItem).where(PersonaPendingItem.doctor_id == doctor_id)
        .order_by(PersonaPendingItem.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    pending_persona_data = [
        {"id": pp.id, "field": pp.field, "proposed_rule": (pp.proposed_rule or "")[:200],
         "summary": (pp.summary or "")[:200], "confidence": pp.confidence,
         "status": pp.status, "created_at": _fmt_ts(pp.created_at)}
        for pp in pending_persona
    ]

    return {
        "profile": profile,
        "patients": {"count": len(patients_data), "items": patients_data},
        "records": {"count": len(records_data), "items": records_data},
        "tasks": {"count": len(tasks_data), "items": tasks_data},
        "knowledge": {"count": len(kb_data), "items": kb_data},
        "chats": {"count": len(chats_data), "items": chats_data},
        "interviews": {"count": len(interviews_data), "items": interviews_data},
        "suggestions": {"count": len(suggestions_data), "items": suggestions_data},
        "drafts": {"count": len(drafts_data), "items": drafts_data},
        "messages": {"count": len(messages_data), "items": messages_data},
        "persona": {"count": 1 if persona_data else 0, "item": persona_data},
        "preferences": {"count": 1 if prefs_data else 0, "item": prefs_data},
        "edits": {"count": len(edits_data), "items": edits_data},
        "kb_usage": {"count": len(kb_usage_data), "items": kb_usage_data},
        "wechat": {"count": 1 if wechat_data else 0, "item": wechat_data},
        "invite_codes": {"count": len(invites_data), "items": invites_data},
        "audit_log": {"count": len(audits_data), "items": audits_data},
        "pending_persona": {"count": len(pending_persona_data), "items": pending_persona_data},
    }


# ---------------------------------------------------------------------------
# GET /api/admin/patients/{patient_id}/related
# ---------------------------------------------------------------------------

@router.get("/api/admin/patients/{patient_id}/related")
async def admin_patient_related(
    patient_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    """All related data for a patient across every table."""
    LIMIT = 50

    patient = (
        await db.execute(select(Patient).where(Patient.id == patient_id))
    ).scalars().first()
    if not patient:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Patient not found")

    profile = {
        "id": patient.id, "doctor_id": patient.doctor_id,
        "name": patient.name, "gender": patient.gender,
        "year_of_birth": patient.year_of_birth, "phone": patient.phone or "",
        "created_at": _fmt_ts(patient.created_at),
        "last_activity_at": _fmt_ts(patient.last_activity_at),
    }

    # Doctor name
    doctor = (await db.execute(
        select(Doctor.name).where(Doctor.doctor_id == patient.doctor_id)
    )).scalar()
    profile["doctor_name"] = doctor or patient.doctor_id

    # Medical records
    records = (await db.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.patient_id == patient_id)
        .order_by(MedicalRecordDB.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    records_data = [
        {"id": r.id, "record_type": r.record_type,
         "content": (r.content or "")[:200], "status": r.status,
         "diagnosis": (r.diagnosis or "")[:200],
         "created_at": _fmt_ts(r.created_at)}
        for r in records
    ]

    # Messages
    messages = (await db.execute(
        select(PatientMessage).where(PatientMessage.patient_id == patient_id)
        .order_by(PatientMessage.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    messages_data = [
        {"id": m.id, "direction": m.direction, "source": m.source,
         "content": (m.content or "")[:200],
         "created_at": _fmt_ts(m.created_at)}
        for m in messages
    ]

    # Tasks
    tasks = (await db.execute(
        select(DoctorTask).where(DoctorTask.patient_id == patient_id)
        .order_by(DoctorTask.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    tasks_data = [
        {"id": t.id, "task_type": t.task_type, "title": t.title,
         "status": t.status, "due_at": _fmt_ts(t.due_at),
         "created_at": _fmt_ts(t.created_at)}
        for t in tasks
    ]

    # AI suggestions (via records)
    record_ids = [r.id for r in records]
    suggestions_data = []
    if record_ids:
        suggestions = (await db.execute(
            select(AISuggestion).where(AISuggestion.record_id.in_(record_ids))
            .order_by(AISuggestion.created_at.desc()).limit(LIMIT)
        )).scalars().all()
        suggestions_data = [
            {"id": s.id, "record_id": s.record_id, "section": s.section,
             "content": (s.content or "")[:200], "decision": s.decision,
             "created_at": _fmt_ts(s.created_at)}
            for s in suggestions
        ]

    # Interview sessions
    interviews = (await db.execute(
        select(InterviewSessionDB).where(InterviewSessionDB.patient_id == patient_id)
        .order_by(InterviewSessionDB.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    interviews_data = [
        {"id": s.id[:8], "doctor_id": s.doctor_id, "status": s.status,
         "turn_count": s.turn_count, "created_at": _fmt_ts(s.created_at)}
        for s in interviews
    ]

    # Message drafts
    drafts = (await db.execute(
        select(MessageDraft).where(
            MessageDraft.patient_id == str(patient_id)
        ).order_by(MessageDraft.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    drafts_data = [
        {"id": d.id, "status": d.status,
         "draft_text": (d.draft_text or "")[:200],
         "created_at": _fmt_ts(d.created_at)}
        for d in drafts
    ]

    # Patient auth
    auth = (await db.execute(
        select(PatientAuth).where(PatientAuth.patient_id == patient_id)
    )).scalars().first()
    auth_data = None
    if auth:
        auth_data = {
            "patient_id": auth.patient_id,
            "access_code": auth.access_code[:6] + "***",
            "access_code_version": auth.access_code_version,
            "created_at": _fmt_ts(auth.created_at),
        }

    # Knowledge usage (for this patient)
    kb_usage = (await db.execute(
        select(KnowledgeUsageLog).where(KnowledgeUsageLog.patient_id == str(patient_id))
        .order_by(KnowledgeUsageLog.created_at.desc()).limit(LIMIT)
    )).scalars().all()
    kb_usage_data = [
        {"id": u.id, "knowledge_item_id": u.knowledge_item_id,
         "usage_context": u.usage_context, "record_id": u.record_id,
         "created_at": _fmt_ts(u.created_at)}
        for u in kb_usage
    ]

    return {
        "profile": profile,
        "records": {"count": len(records_data), "items": records_data},
        "messages": {"count": len(messages_data), "items": messages_data},
        "tasks": {"count": len(tasks_data), "items": tasks_data},
        "suggestions": {"count": len(suggestions_data), "items": suggestions_data},
        "interviews": {"count": len(interviews_data), "items": interviews_data},
        "drafts": {"count": len(drafts_data), "items": drafts_data},
        "auth": {"count": 1 if auth_data else 0, "item": auth_data},
        "kb_usage": {"count": len(kb_usage_data), "items": kb_usage_data},
    }
