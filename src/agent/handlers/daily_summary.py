"""Handler for daily_summary intent — today's briefing via chat."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext
from db.engine import AsyncSessionLocal
from db.models.patient import Patient
from db.models.records import MedicalRecordDB
from db.models.tasks import DoctorTask, TaskStatus
from utils.log import log


def _start_of_today_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@register(IntentType.daily_summary)
async def handle_daily_summary(ctx: TurnContext) -> HandlerResult:
    """Generate a daily summary for the doctor: tasks, patients, records."""
    today_start = _start_of_today_utc()

    try:
        async with AsyncSessionLocal() as db:
            # 1. Overdue tasks
            overdue_stmt = (
                select(DoctorTask, Patient.name)
                .outerjoin(Patient, DoctorTask.patient_id == Patient.id)
                .where(
                    DoctorTask.doctor_id == ctx.doctor_id,
                    DoctorTask.status == TaskStatus.pending,
                    DoctorTask.due_at < today_start,
                    DoctorTask.due_at.isnot(None),
                )
                .order_by(DoctorTask.due_at.asc())
                .limit(20)
            )
            overdue_rows = (await db.execute(overdue_stmt)).all()

            # 2. Pending tasks
            pending_stmt = (
                select(func.count())
                .select_from(DoctorTask)
                .where(
                    DoctorTask.doctor_id == ctx.doctor_id,
                    DoctorTask.status == TaskStatus.pending,
                )
            )
            pending_count: int = (await db.execute(pending_stmt)).scalar_one()

            # 3. Completed today
            completed_stmt = (
                select(func.count())
                .select_from(DoctorTask)
                .where(
                    DoctorTask.doctor_id == ctx.doctor_id,
                    DoctorTask.status == TaskStatus.completed,
                    DoctorTask.updated_at >= today_start,
                )
            )
            completed_today: int = (await db.execute(completed_stmt)).scalar_one()

            # 4. Today's patients
            today_patients_stmt = (
                select(func.count(func.distinct(MedicalRecordDB.patient_id)))
                .where(
                    MedicalRecordDB.doctor_id == ctx.doctor_id,
                    MedicalRecordDB.created_at >= today_start,
                )
            )
            today_patients: int = (await db.execute(today_patients_stmt)).scalar_one()

    except Exception as exc:
        log(f"[daily_summary] DB query failed: {exc}", level="warning")
        return HandlerResult(reply="抱歉，暂时无法获取今日摘要，请稍后再试。")

    # ── Compose reply ────────────────────────────────────────────────
    lines = ["📋 **今日摘要**", ""]

    # Overdue
    if overdue_rows:
        lines.append(f"⚠️ 逾期任务 ({len(overdue_rows)})：")
        for task, patient_name in overdue_rows[:5]:
            overdue_days = (today_start - task.due_at).days
            name = patient_name or "未知患者"
            lines.append(f"  - {name}：{task.title}（逾期{overdue_days}天）")
        if len(overdue_rows) > 5:
            lines.append(f"  - …还有 {len(overdue_rows) - 5} 项")
        lines.append("")

    # Stats
    lines.append(f"📊 待处理任务：{pending_count}")
    lines.append(f"✅ 今日已完成：{completed_today}")
    lines.append(f"👤 今日接诊患者：{today_patients}")

    if not overdue_rows and pending_count == 0 and today_patients == 0:
        lines.append("")
        lines.append("今日暂无待办事项，一切正常。")

    return HandlerResult(reply="\n".join(lines))
