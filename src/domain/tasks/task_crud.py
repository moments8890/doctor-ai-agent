"""
任务创建、通知发送。
"""

from __future__ import annotations

import os
import asyncio
import inspect
from datetime import datetime, timezone
from typing import Optional, Dict, List

from db.engine import AsyncSessionLocal
from db.crud import (
    create_task,
    get_due_tasks,
    mark_task_notified,
    revert_task_to_pending,
)
from db.models import DoctorTask
from domain.tasks.notifications import send_doctor_notification
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


async def send_task_notification(doctor_id: str, task: DoctorTask) -> None:
    icon = _TASK_ICONS.get(task.task_type, "📌")
    lines = [f"{icon} 【{task.title}】"]
    if task.content:
        lines.append(task.content)
    if task.due_at:
        lines.append(f"⏰ 预定时间：{task.due_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"\n回复「完成 {task.id}」标记完成")
    message = "\n".join(lines)

    # Claim-before-send: atomically set notified_at.
    # If another worker already claimed this task, skip silently.
    async with AsyncSessionLocal() as session:
        claimed = await mark_task_notified(session, task.id)
    if not claimed:
        return  # another worker already notified this task

    retries = _notify_retry_count()
    delay_seconds = _notify_retry_delay_seconds()
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            await send_doctor_notification(doctor_id, message)
            break
        except Exception as e:
            last_error = e
            await _emit_task_log(
                "task_notify_attempt_failed",
                task_id=task.id,
                doctor_id=doctor_id,
                task_type=task.task_type,
                attempt=attempt,
                retries=retries,
                error=str(e),
            )
            if attempt < retries and delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
    else:
        # All send attempts failed — clear notified_at so the next cycle
        # can retry. This is the safer direction: at worst a notification is
        # missed this cycle, not duplicated.
        async with AsyncSessionLocal() as session:
            await revert_task_to_pending(session, task.id)
        raise RuntimeError(
            f"task notification failed after {retries} attempt(s) for task_id={task.id}"
        ) from last_error

    await _emit_task_log(
        "task_notified",
        task_id=task.id,
        doctor_id=doctor_id,
        task_type=task.task_type,
    )


async def check_and_send_due_tasks() -> None:
    """APScheduler job: query pending due tasks and send WeChat notifications."""
    await run_due_task_cycle()


async def _fetch_and_filter_tasks(
    doctor_id: Optional[str],
    now: datetime,
    include_manual: bool,
    force: bool,
) -> tuple[List[DoctorTask], List[DoctorTask]]:
    """拉取到期任务并按医生通知偏好筛选；返回 (all_tasks, eligible_tasks)。"""
    async with AsyncSessionLocal() as session:
        tasks = await get_due_tasks(session, now)
    if doctor_id:
        tasks = [t for t in tasks if t.doctor_id == doctor_id]

    tasks_by_doctor: Dict[str, List[DoctorTask]] = {}
    for task in tasks:
        tasks_by_doctor.setdefault(task.doctor_id, []).append(task)

    # DoctorNotifyPreference table removed — all doctors are always allowed.
    allowed_doctors = set(tasks_by_doctor.keys())

    filtered_tasks = [t for t in tasks if t.doctor_id in allowed_doctors]
    return tasks, filtered_tasks


async def _send_eligible_tasks(filtered_tasks: List[DoctorTask]) -> tuple[int, int]:
    """依次发送通知给所有合格任务；返回 (success_count, failed_count)。"""
    success_count = 0
    failed_count = 0
    for task in filtered_tasks:
        try:
            await send_task_notification(task.doctor_id, task)
            success_count += 1
        except Exception as e:
            failed_count += 1
            await _emit_task_log(
                "task_notify_failed",
                task_id=task.id,
                doctor_id=task.doctor_id,
                task_type=task.task_type,
                error=str(e),
            )
    return success_count, failed_count


async def run_due_task_cycle(
    doctor_id: Optional[str] = None,
    *,
    include_manual: bool = False,
    force: bool = False,
) -> dict:
    """Run one due-task notification cycle and return summary stats."""
    await _emit_task_log("scheduler_tick_start", level="debug")
    now = datetime.now(timezone.utc)

    tasks, filtered_tasks = await _fetch_and_filter_tasks(
        doctor_id, now, include_manual, force
    )
    due_count = len(tasks)
    eligible_count = len(filtered_tasks)
    if due_count > 0:
        await _emit_task_log("scheduler_due_tasks", count=due_count, eligible_count=eligible_count)
    else:
        await _emit_task_log("scheduler_due_tasks", level="debug", count=0)

    success_count, failed_count = await _send_eligible_tasks(filtered_tasks)
    return {
        "due_count": due_count,
        "eligible_count": eligible_count,
        "sent_count": success_count,
        "failed_count": failed_count,
    }
