"""Briefing endpoint: overdue tasks, today's completions.

Phase 1 — database-driven only. LLM-driven insights (trend detection,
pattern recognition) will be added in a future phase.

ReviewQueue and DiagnosisResult tables have been removed. Pending-review
cards are no longer generated from those tables.
"""
from __future__ import annotations

import json as _json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, Query
from sqlalchemy import func, select

from channels.web.ui._utils import _resolve_ui_doctor_id
from db.engine import AsyncSessionLocal
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
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
            context_parts = [f"\u900e\u671f{overdue_days}\u5929"] if overdue_days > 0 else ["\u900e\u671f"]
            context_parts.append("\u5efa\u8bae\u5c3d\u5feb\u5904\u7406")
            display_name = patient_name or "\u672a\u77e5\u60a3\u8005"
            cards.append({
                "type": "urgent",
                "title": f"{display_name} {task.title}",
                "context": " \u00b7 ".join(context_parts),
                "task_id": task.id,
                "patient_id": task.patient_id,
                "actions": ["complete", "postpone", "view"],
            })

        # ---- 2. Completed today ----
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

        # ---- 3. Today's pending tasks ----
        today_tasks_stmt = (
            select(func.count())
            .select_from(DoctorTask)
            .where(
                DoctorTask.doctor_id == resolved,
                DoctorTask.status == TaskStatus.pending,
            )
        )
        today_tasks: int = (await db.execute(today_tasks_stmt)).scalar_one()

        # ---- 4. Today's patients (records created today) ----
        today_patients_stmt = (
            select(func.count(func.distinct(MedicalRecordDB.patient_id)))
            .where(
                MedicalRecordDB.doctor_id == resolved,
                MedicalRecordDB.created_at >= today_start,
            )
        )
        today_patients: int = (await db.execute(today_patients_stmt)).scalar_one()

    return {
        "cards": cards,
        "stats": {
            "today_patients": today_patients,
            "today_tasks": today_tasks,
            "completed_today": completed_today,
        },
        "completed_today": completed_today,
    }
