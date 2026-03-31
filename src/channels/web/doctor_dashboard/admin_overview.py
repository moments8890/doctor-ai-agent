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
    SuggestionDecision,
    Doctor,
    DoctorKnowledgeItem,
    DoctorTask,
    MedicalRecordDB,
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
    """Aggregated platform stats + alert items for the overview dashboard."""
    cutoff_24h = _cutoff_24h()
    cutoff_3d = _cutoff_days(3)

    # Active doctors (ever logged in / have patients)
    active_doctors_count = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(Doctor),
                Doctor.doctor_id,
            )
        )
    ).scalar() or 0

    # Messages in last 24h
    msgs_24h = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(PatientMessage).where(
                    PatientMessage.created_at >= cutoff_24h
                ),
                PatientMessage.doctor_id,
            )
        )
    ).scalar() or 0

    # Records in last 24h
    records_24h = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(MedicalRecordDB).where(
                    MedicalRecordDB.created_at >= cutoff_24h
                ),
                MedicalRecordDB.doctor_id,
            )
        )
    ).scalar() or 0

    # AI suggestions breakdown (all-time)
    ai_rows = (
        await db.execute(
            apply_exclude_test_doctors(
                select(AISuggestion.decision, func.count().label("cnt"))
                .group_by(AISuggestion.decision),
                AISuggestion.doctor_id,
            )
        )
    ).all()
    ai_breakdown: dict = {}
    ai_total = 0
    for decision, cnt in ai_rows:
        key = decision if decision else "undecided"
        ai_breakdown[key] = cnt
        ai_total += cnt

    # Pending tasks (all doctors)
    pending_tasks_count = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(DoctorTask).where(
                    DoctorTask.status == TaskStatus.pending
                ),
                DoctorTask.doctor_id,
            )
        )
    ).scalar() or 0

    # Overdue tasks (due_at < now, still pending)
    overdue_count = (
        await db.execute(
            apply_exclude_test_doctors(
                select(func.count()).select_from(DoctorTask).where(
                    and_(
                        DoctorTask.status == TaskStatus.pending,
                        DoctorTask.due_at != None,  # noqa: E711
                        DoctorTask.due_at < _now_utc(),
                    )
                ),
                DoctorTask.doctor_id,
            )
        )
    ).scalar() or 0

    # Alerts: sample overdue task records
    overdue_tasks_rows = (
        await db.execute(
            apply_exclude_test_doctors(
                select(DoctorTask).where(
                    and_(
                        DoctorTask.status == TaskStatus.pending,
                        DoctorTask.due_at != None,  # noqa: E711
                        DoctorTask.due_at < _now_utc(),
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

    # Alerts: inactive doctors (updated_at > 3 days ago or no recent patients)
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

    # AI suggestions summary
    ai_accepted = ai_breakdown.get(SuggestionDecision.confirmed, 0) + ai_breakdown.get("confirmed", 0)
    ai_edited = ai_breakdown.get(SuggestionDecision.edited, 0) + ai_breakdown.get("edited", 0)
    ai_rejected = ai_breakdown.get(SuggestionDecision.rejected, 0) + ai_breakdown.get("rejected", 0)

    # LLM calls in last hour (read from jsonl log)
    llm_calls_1h = 0
    llm_errors = 0
    try:
        import json as _json
        llm_log = Path(__file__).resolve().parents[4] / "logs" / "llm_calls.jsonl"
        if llm_log.exists():
            hour_ago_iso = (_now_utc() - timedelta(hours=1)).isoformat()
            with open(llm_log, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = _json.loads(line)
                        if entry.get("timestamp", "") >= hour_ago_iso:
                            llm_calls_1h += 1
                            if entry.get("status") == "error":
                                llm_errors += 1
                    except (ValueError, _json.JSONDecodeError):
                        pass
    except OSError:
        pass

    return {
        "stats": {
            "active_doctors": active_doctors_count,
            "total_doctors": active_doctors_count,
            "messages_24h": msgs_24h,
            "records_24h": records_24h,
            "suggestions_24h": ai_total,
            "suggestions_detail": f"采纳{ai_accepted} 编辑{ai_edited} 拒绝{ai_rejected}",
            "pending_tasks": pending_tasks_count,
            "overdue_tasks": overdue_count,
            "tasks_detail": f"逾期{overdue_count}" if overdue_count else "",
            "llm_calls_1h": llm_calls_1h,
            "llm_detail": f"err {llm_errors}" if llm_errors else "",
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
