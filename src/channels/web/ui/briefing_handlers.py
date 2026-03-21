"""Briefing endpoint: overdue tasks, pending reviews, today's completions.

Phase 1 — database-driven only. LLM-driven insights (trend detection,
pattern recognition) will be added in a future phase.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, Query
from sqlalchemy import func, select

from channels.web.ui._utils import _resolve_ui_doctor_id
from db.engine import AsyncSessionLocal
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from db.models.review_queue import ReviewQueue
from db.models.tasks import DoctorTask, TaskStatus
from infra.auth.rate_limit import enforce_doctor_rate_limit

router = APIRouter(tags=["ui"], include_in_schema=False)


def _start_of_today_utc() -> datetime:
    """Return midnight UTC for the current date."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/api/doctor/briefing", include_in_schema=True)
async def get_briefing(
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """Return briefing cards for the doctor landing page.

    Cards:
    - **urgent**: overdue tasks (status=pending, due_at < today)
    - **pending_review**: interview records awaiting review
    - **completed_today**: count of tasks completed today
    """
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(resolved, scope="ui.briefing")

    today_start = _start_of_today_utc()
    cards: list[dict] = []

    async with AsyncSessionLocal() as db:
        # ---- 1. Overdue tasks (pending + due_at < today) ----
        overdue_stmt = (
            select(DoctorTask, Patient.name)
            .outerjoin(Patient, DoctorTask.patient_id == Patient.id)
            .where(
                DoctorTask.doctor_id == resolved,
                DoctorTask.status == TaskStatus.pending,
                DoctorTask.due_at < today_start,
                DoctorTask.due_at.isnot(None),
            )
            .order_by(DoctorTask.due_at.asc())
            .limit(20)
        )
        overdue_rows = (await db.execute(overdue_stmt)).all()

        for task, patient_name in overdue_rows:
            overdue_days = (today_start - task.due_at).days
            context_parts = [f"逾期{overdue_days}天"] if overdue_days > 0 else ["逾期"]
            context_parts.append("建议尽快处理")
            cards.append({
                "type": "urgent",
                "title": f"{patient_name or '未知患者'} {task.title}",
                "context": " · ".join(context_parts),
                "task_id": task.id,
                "patient_id": task.patient_id,
                "actions": ["complete", "postpone", "view"],
            })

        # ---- 2. Pending review items ----
        review_stmt = (
            select(ReviewQueue, Patient.name, MedicalRecordDB.structured)
            .outerjoin(Patient, ReviewQueue.patient_id == Patient.id)
            .outerjoin(MedicalRecordDB, ReviewQueue.record_id == MedicalRecordDB.id)
            .where(
                ReviewQueue.doctor_id == resolved,
                ReviewQueue.status == "pending_review",
            )
            .order_by(ReviewQueue.created_at.desc())
            .limit(50)
        )
        review_rows = (await db.execute(review_stmt)).all()

        if review_rows:
            items = []
            for rq, patient_name, structured_json in review_rows:
                chief_complaint = ""
                if structured_json:
                    try:
                        s = _json.loads(structured_json)
                        chief_complaint = s.get("chief_complaint", "")
                    except (ValueError, TypeError):
                        pass
                items.append({
                    "patient_name": patient_name or "未知患者",
                    "chief_complaint": chief_complaint,
                    "record_id": rq.record_id,
                    "queue_id": rq.id,
                })
            cards.append({
                "type": "pending_review",
                "title": f"{len(items)}条问诊待审核",
                "items": items,
            })

        # ---- 3. Completed today ----
        completed_stmt = (
            select(func.count())
            .select_from(DoctorTask)
            .where(
                DoctorTask.doctor_id == resolved,
                DoctorTask.status == TaskStatus.completed,
                DoctorTask.updated_at >= today_start,
            )
        )
        completed_today: int = (await db.execute(completed_stmt)).scalar_one()

        # ---- 4. Today's pending tasks ----
        today_tasks_stmt = (
            select(func.count())
            .select_from(DoctorTask)
            .where(
                DoctorTask.doctor_id == resolved,
                DoctorTask.status == TaskStatus.pending,
            )
        )
        today_tasks: int = (await db.execute(today_tasks_stmt)).scalar_one()

        # ---- 5. Today's patients (records created today) ----
        today_patients_stmt = (
            select(func.count(func.distinct(MedicalRecordDB.patient_id)))
            .where(
                MedicalRecordDB.doctor_id == resolved,
                MedicalRecordDB.created_at >= today_start,
            )
        )
        today_patients: int = (await db.execute(today_patients_stmt)).scalar_one()

        # ---- 6. Red flags count ----
        pending_review_count = len(review_rows) if review_rows else 0
        red_flag_count = 0
        # Count reviews with red_flags from diagnosis
        try:
            from db.models.diagnosis_result import DiagnosisResult
            for rq, _, _ in (review_rows or []):
                diag_row = (await db.execute(
                    select(DiagnosisResult.red_flags).where(DiagnosisResult.record_id == rq.record_id)
                )).scalar_one_or_none()
                if diag_row:
                    flags = _json.loads(diag_row) if isinstance(diag_row, str) else diag_row
                    if flags and len(flags) > 0:
                        red_flag_count += 1
        except Exception:
            pass

    return {
        "cards": cards,
        "stats": {
            "pending_review": pending_review_count,
            "today_patients": today_patients,
            "today_tasks": today_tasks,
            "completed_today": completed_today,
            "red_flags": red_flag_count,
        },
        "completed_today": completed_today,
    }
