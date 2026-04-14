"""
任务创建、逾期摘要通知发送。

Scheduler calls ``check_and_send_due_tasks()`` once daily at 08:30.
It queries *overdue* tasks (due_at < today, status=pending, notified_at IS NULL),
groups them by doctor, and sends ONE consolidated digest per doctor.
"""

from __future__ import annotations

import os
import asyncio
import inspect
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

from db.engine import AsyncSessionLocal
from db.crud import (
    create_task,
    get_overdue_unnotified_tasks,
    bulk_mark_notified,
)
from db.models import DoctorTask
from db.models.patient import Patient
from domain.tasks.notifications import send_digest_notification
from utils.log import task_log

_TASK_ICONS = {
    "general": "📌",
}


async def _emit_task_log(event: str, **kwargs) -> None:
    """Emit task log and safely await if tests patch it with AsyncMock."""
    maybe_awaitable = task_log(event, **kwargs)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


def _notify_retry_count() -> int:
    raw = os.environ.get("TASK_NOTIFY_RETRY_COUNT", "3")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 3


def _notify_retry_delay_seconds() -> float:
    raw = os.environ.get("TASK_NOTIFY_RETRY_DELAY_SECONDS", "1")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 1.0


async def create_general_task(
    doctor_id: str,
    title: str,
    patient_id: Optional[int] = None,
    content: Optional[str] = None,
) -> DoctorTask:
    """Create a generic informational task (e.g. auto-save notifications)."""
    async with AsyncSessionLocal() as session:
        task = await create_task(
            session,
            doctor_id=doctor_id,
            task_type="general",
            title=title,
            content=content,
            patient_id=patient_id,
            record_id=None,
            due_at=None,
        )
    return task


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------

def _today_start_utc() -> datetime:
    """Return midnight UTC of the current day."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _overdue_days(due_at: datetime, today_start: datetime) -> int:
    """Number of full days a task is overdue (minimum 1)."""
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    delta = today_start - due_at
    return max(1, delta.days)


async def _resolve_patient_names(patient_ids: set[int]) -> Dict[int, str]:
    """Batch-fetch patient names for a set of IDs."""
    if not patient_ids:
        return {}
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Patient.id, Patient.name).where(Patient.id.in_(patient_ids))
        )
        return {row.id: row.name for row in result}


def _build_task_line(
    task: DoctorTask,
    patient_names: Dict[int, str],
    today_start: datetime,
) -> str:
    """Format one bullet line for the digest message."""
    name = patient_names.get(task.patient_id, "未知患者") if task.patient_id else "未关联患者"
    days = _overdue_days(task.due_at, today_start)  # type: ignore[arg-type]
    return f"· {name} — {task.title}（逾期{days}天）"


# ---------------------------------------------------------------------------
# Core digest cycle
# ---------------------------------------------------------------------------

async def check_and_send_due_tasks() -> None:
    """APScheduler job: daily overdue digest at 08:30."""
    await run_due_task_cycle()


async def run_due_task_cycle(
    doctor_id: Optional[str] = None,
) -> dict:
    """Query overdue unnotified tasks, group by doctor, send one digest each.

    Returns summary stats for observability.
    """
    await _emit_task_log("digest_cycle_start", level="debug")
    today_start = _today_start_utc()

    # 1. Fetch all overdue unnotified tasks
    async with AsyncSessionLocal() as session:
        tasks = await get_overdue_unnotified_tasks(session, today_start)
    if doctor_id:
        tasks = [t for t in tasks if t.doctor_id == doctor_id]

    if not tasks:
        await _emit_task_log("digest_cycle_no_overdue", level="debug")
        return {"overdue_count": 0, "doctors_notified": 0, "failed_count": 0}

    # 2. Group by doctor
    by_doctor: Dict[str, List[DoctorTask]] = defaultdict(list)
    for task in tasks:
        by_doctor[task.doctor_id].append(task)

    # 3. Resolve patient names in bulk
    all_patient_ids = {t.patient_id for t in tasks if t.patient_id}
    patient_names = await _resolve_patient_names(all_patient_ids)

    await _emit_task_log(
        "digest_cycle_overdue",
        count=len(tasks),
        doctors=len(by_doctor),
    )

    # 4. Send one digest per doctor
    retries = _notify_retry_count()
    delay_seconds = _notify_retry_delay_seconds()
    doctors_notified = 0
    failed_count = 0

    for doc_id, doc_tasks in by_doctor.items():
        task_lines = [
            _build_task_line(t, patient_names, today_start) for t in doc_tasks
        ]
        count = len(doc_tasks)

        last_error = None
        send_ok = False
        for attempt in range(1, retries + 1):
            try:
                await send_digest_notification(doc_id, task_lines, count)
                send_ok = True
                break
            except Exception as e:
                last_error = e
                await _emit_task_log(
                    "digest_send_attempt_failed",
                    doctor_id=doc_id,
                    attempt=attempt,
                    retries=retries,
                    error=str(e),
                )
                if attempt < retries and delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)

        if send_ok:
            # Mark all tasks in this digest as notified
            task_ids = [t.id for t in doc_tasks]
            async with AsyncSessionLocal() as session:
                await bulk_mark_notified(session, task_ids)
            doctors_notified += 1
            await _emit_task_log(
                "digest_sent",
                doctor_id=doc_id,
                task_count=count,
            )
        else:
            failed_count += 1
            await _emit_task_log(
                "digest_send_failed",
                doctor_id=doc_id,
                task_count=count,
                error=str(last_error),
            )

    return {
        "overdue_count": len(tasks),
        "doctors_notified": doctors_notified,
        "failed_count": failed_count,
    }
