from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from db.engine import AsyncSessionLocal
from db.crud import create_task, get_due_tasks, mark_task_notified
from db.models import DoctorTask
from services.wechat_notify import _send_customer_service_msg
from utils.log import log

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
    due_at = datetime.utcnow() + timedelta(days=days)
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
    log(f"[Tasks] created follow_up task id={task.id} due={due_at.date()} for {patient_name}")
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
    log(f"[Tasks] created emergency task id={task.id} for {patient_name}")
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
    log(f"[Tasks] created appointment task id={task.id} due={due_at} for {patient_name}")
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

    await _send_customer_service_msg(doctor_id, message)

    async with AsyncSessionLocal() as session:
        await mark_task_notified(session, task.id)

    log(f"[Tasks] notified doctor {doctor_id} for task id={task.id}")


async def check_and_send_due_tasks() -> None:
    """APScheduler job: query pending due tasks and send WeChat notifications."""
    log("[Tasks] scheduler tick — checking due tasks")
    now = datetime.utcnow()
    async with AsyncSessionLocal() as session:
        tasks = await get_due_tasks(session, now)

    log(f"[Tasks] found {len(tasks)} due task(s)")
    for task in tasks:
        try:
            await send_task_notification(task.doctor_id, task)
        except Exception as e:
            log(f"[Tasks] failed to notify task id={task.id}: {e}")
