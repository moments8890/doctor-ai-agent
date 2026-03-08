"""
任务创建、随访通知发送和调度器租约管理。
"""

from __future__ import annotations

import re
import os
import asyncio
import socket
import inspect
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List

from db.engine import AsyncSessionLocal
from db.crud import (
    create_task,
    get_due_tasks,
    mark_task_notified,
    get_doctor_notify_preference,
    upsert_doctor_notify_preference,
    try_acquire_scheduler_lease,
    release_scheduler_lease,
)
from db.models import DoctorTask
from services.notify.notification import send_doctor_notification
from services.notify.notify_control import should_auto_run_now
from utils.log import task_log

# Chinese digit → integer mapping
_CN_DIGITS = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_TASK_ICONS = {
    "follow_up": "🔔",
    "emergency": "🚨",
    "appointment": "📅",
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


def _parse_cn_or_int(raw: str) -> Optional[int]:
    """Parse a string that may be a Chinese digit word or an integer."""
    n = _CN_DIGITS.get(raw)
    if n is not None:
        return n
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def extract_follow_up_days(follow_up_plan: str) -> int:
    """Extract the number of days until follow-up from a free-text plan.

    Supports: N天, N周, N个月, Chinese digit words (两/三/…), 下周, 明天.
    Returns 7 (days) as the default fallback.
    """
    if not follow_up_plan:
        return 7

    # 明天
    if "明天" in follow_up_plan:
        return 1

    # 下周 / 下星期
    if "下周" in follow_up_plan or "下星期" in follow_up_plan:
        return 7

    # N周
    m = re.search(r'([一两二三四五六七八九十\d]+)周', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n * 7

    # N个月
    m = re.search(r'([一两二三四五六七八九十\d]+)个月', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n * 30

    # N天
    m = re.search(r'([一两二三四五六七八九十\d]+)天', follow_up_plan)
    if m:
        n = _parse_cn_or_int(m.group(1))
        if n is not None:
            return n

    return 7


async def create_follow_up_task(
    doctor_id: str,
    record_id: int,
    patient_name: str,
    follow_up_plan: str,
    patient_id: Optional[int] = None,
) -> DoctorTask:
    days = extract_follow_up_days(follow_up_plan)
    due_at = datetime.now(timezone.utc) + timedelta(days=days)
    title = f"随访提醒：{patient_name}"
    content = follow_up_plan

    async with AsyncSessionLocal() as session:
        task = await create_task(
            session,
            doctor_id=doctor_id,
            task_type="follow_up",
            title=title,
            content=content,
            patient_id=patient_id,
            record_id=record_id,
            due_at=due_at,
        )
    await _emit_task_log(
        "task_created",
        task_type="follow_up",
        task_id=task.id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        record_id=record_id,
        due_at=due_at.isoformat(),
    )
    return task


async def create_emergency_task(
    doctor_id: str,
    record_id: int,
    patient_name: str,
    diagnosis: Optional[str] = None,
    patient_id: Optional[int] = None,
) -> DoctorTask:
    title = f"紧急记录：{patient_name}"
    content = diagnosis

    async with AsyncSessionLocal() as session:
        task = await create_task(
            session,
            doctor_id=doctor_id,
            task_type="emergency",
            title=title,
            content=content,
            patient_id=patient_id,
            record_id=record_id,
            due_at=None,
        )
    await _emit_task_log(
        "task_created",
        task_type="emergency",
        task_id=task.id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        record_id=record_id,
    )
    await send_task_notification(doctor_id, task)
    return task


async def create_appointment_task(
    doctor_id: str,
    patient_name: str,
    appointment_dt: datetime,
    notes: Optional[str] = None,
    patient_id: Optional[int] = None,
) -> DoctorTask:
    due_at = appointment_dt - timedelta(hours=1)
    title = f"预约提醒：{patient_name}"
    content = notes

    async with AsyncSessionLocal() as session:
        task = await create_task(
            session,
            doctor_id=doctor_id,
            task_type="appointment",
            title=title,
            content=content,
            patient_id=patient_id,
            record_id=None,
            due_at=due_at,
        )
    await _emit_task_log(
        "task_created",
        task_type="appointment",
        task_id=task.id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        due_at=due_at.isoformat(),
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
        raise RuntimeError(
            f"task notification failed after {retries} attempt(s) for task_id={task.id}"
        ) from last_error

    async with AsyncSessionLocal() as session:
        await mark_task_notified(session, task.id)

    await _emit_task_log(
        "task_notified",
        task_id=task.id,
        doctor_id=doctor_id,
        task_type=task.task_type,
    )


async def check_and_send_due_tasks() -> None:
    """APScheduler job: query pending due tasks and send WeChat notifications."""
    await run_due_task_cycle()


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
    lease_acquired = False
    lease_enabled = (
        use_scheduler_lease
        and _scheduler_lease_enabled()
        and doctor_id is None
    )
    owner_id = _scheduler_owner_id()

    if lease_enabled:
        try:
            async with AsyncSessionLocal() as session:
                lease_acquired = await try_acquire_scheduler_lease(
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
            lease_acquired = True
        if not lease_acquired:
            await _emit_task_log(
                "scheduler_tick_skipped_lease_not_acquired",
                owner_id=owner_id,
            )
            return {
                "due_count": 0,
                "eligible_count": 0,
                "sent_count": 0,
                "failed_count": 0,
                "skipped_by_lease": True,
            }

    try:
        async with AsyncSessionLocal() as session:
            tasks = await get_due_tasks(session, now)

        if doctor_id:
            tasks = [t for t in tasks if t.doctor_id == doctor_id]

        tasks_by_doctor: Dict[str, List[DoctorTask]] = {}
        for task in tasks:
            tasks_by_doctor.setdefault(task.doctor_id, []).append(task)

        allowed_doctors = set()
        for did in tasks_by_doctor.keys():
            try:
                async with AsyncSessionLocal() as session:
                    pref = await get_doctor_notify_preference(session, did)
                    if should_auto_run_now(
                        pref, now, include_manual=include_manual, force=force
                    ):
                        allowed_doctors.add(did)
                        await upsert_doctor_notify_preference(
                            session,
                            did,
                            last_auto_run_at=now,
                        )
            except Exception as e:
                await _emit_task_log(
                    "scheduler_pref_check_failed",
                    doctor_id=did,
                    error=str(e),
                )
                allowed_doctors.add(did)

        filtered_tasks = [t for t in tasks if t.doctor_id in allowed_doctors]

        due_count = len(tasks)
        eligible_count = len(filtered_tasks)
        if due_count > 0:
            await _emit_task_log("scheduler_due_tasks", count=due_count, eligible_count=eligible_count)
        else:
            await _emit_task_log("scheduler_due_tasks", level="debug", count=0)
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
        return {
            "due_count": due_count,
            "eligible_count": eligible_count,
            "sent_count": success_count,
            "failed_count": failed_count,
            "skipped_by_lease": False,
        }
    finally:
        if lease_enabled and lease_acquired:
            try:
                async with AsyncSessionLocal() as session:
                    await release_scheduler_lease(
                        session=session,
                        lease_key=_LEASE_KEY,
                        owner_id=owner_id,
                        now=datetime.now(timezone.utc),
                    )
            except Exception as e:
                await _emit_task_log(
                    "scheduler_lease_release_failed",
                    owner_id=owner_id,
                    error=str(e),
                )
