"""
任务创建、通知发送和调度器租约管理。
"""

from __future__ import annotations

import os
import asyncio
import socket
import inspect
from datetime import datetime, timezone
from typing import Optional, Dict, List

from db.engine import AsyncSessionLocal
from db.crud import (
    create_task,
    get_due_tasks,
    mark_task_notified,
    revert_task_to_pending,
    try_acquire_scheduler_lease,
    release_scheduler_lease,
)
from db.models import DoctorTask
from domain.tasks.notifications import send_doctor_notification
from utils.log import task_log

_TASK_ICONS = {
    "general": "📌",
    "review": "📋",
}

_LEASE_KEY = "task_notifier"


async def _emit_task_log(event: str, **kwargs) -> None:
    """Emit task log and safely await if tests patch it with AsyncMock."""
    maybe_awaitable = task_log(event, **kwargs)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


def _scheduler_owner_id() -> str:
    host = socket.gethostname() or "unknown-host"
    pid = os.getpid()
    return "{0}:{1}".format(host, pid)


def _scheduler_lease_enabled() -> bool:
    raw = os.environ.get("TASK_SCHEDULER_LEASE_ENABLED", "true")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _scheduler_lease_ttl_seconds() -> int:
    raw = os.environ.get("TASK_SCHEDULER_LEASE_TTL_SECONDS", "90")
    try:
        return max(10, int(raw))
    except (TypeError, ValueError):
        return 90


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

    # Claim-before-send: atomically transition pending → notified.
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
        # All send attempts failed — revert to 'pending' so the next cycle
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


async def _try_acquire_lease(
    owner_id: str,
    now: datetime,
) -> tuple[bool, bool]:
    """尝试获取调度器租约；返回 (lease_acquired, should_skip)。"""
    try:
        async with AsyncSessionLocal() as session:
            acquired = await try_acquire_scheduler_lease(
                session=session,
                lease_key=_LEASE_KEY,
                owner_id=owner_id,
                now=now,
                lease_ttl_seconds=_scheduler_lease_ttl_seconds(),
            )
    except Exception as e:
        await _emit_task_log(
            "scheduler_lease_acquire_failed_fallback_to_run",
            owner_id=owner_id,
            error=str(e),
        )
        return True, False  # fallback: run anyway
    if not acquired:
        await _emit_task_log(
            "scheduler_tick_skipped_lease_not_acquired",
            owner_id=owner_id,
        )
        return False, True  # skip cycle
    return True, False


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
    use_scheduler_lease: bool = True,
) -> dict:
    """Run one due-task notification cycle and return summary stats."""
    await _emit_task_log("scheduler_tick_start", level="debug")
    now = datetime.now(timezone.utc)
    owner_id = _scheduler_owner_id()
    lease_enabled = use_scheduler_lease and _scheduler_lease_enabled() and doctor_id is None

    if lease_enabled:
        _acquired, should_skip = await _try_acquire_lease(owner_id, now)
        if should_skip:
            return {
                "due_count": 0, "eligible_count": 0,
                "sent_count": 0, "failed_count": 0,
                "skipped_by_lease": True,
            }

    try:
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
            "skipped_by_lease": False,
        }
    finally:
        pass  # Lease expires naturally via TTL; no explicit release needed.
