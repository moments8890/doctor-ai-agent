from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any

from db.crud import (
    get_doctor_notify_preference,
    upsert_doctor_notify_preference,
)
from db.engine import AsyncSessionLocal
from db.models import DoctorNotifyPreference


_MODE_RE = re.compile(r"^\s*通知模式[：:\s]*(自动|手动)\s*$")
_INTERVAL_RE = re.compile(r"^\s*通知频率[：:\s]*(每)?\s*(\d+)\s*分钟\s*$")
_CRON_RE = re.compile(r"^\s*通知计划[：:\s]*(\S+\s+\S+\s+\S+\s+\S+\s+\S+)\s*$")
_IMMEDIATE_RE = re.compile(r"^\s*通知计划[：:\s]*(立即|实时)\s*$")
_SHOW_RE = re.compile(r"^\s*(通知设置|查看通知设置)\s*$")
_TRIGGER_RE = re.compile(r"^\s*(立即发送待办|立即触发通知|发送待办通知)\s*$")
_SIMPLE_CRON_MIN_RE = re.compile(r"^\*/(\d+)\s+\*\s+\*\s+\*\s+\*$")


def parse_notify_command(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    raw = (text or "").strip()
    if not raw:
        return None

    m = _MODE_RE.match(raw)
    if m:
        mode = "auto" if m.group(1) == "自动" else "manual"
        return ("set_mode", {"notify_mode": mode})

    m = _INTERVAL_RE.match(raw)
    if m:
        minutes = int(m.group(2))
        return ("set_interval", {"interval_minutes": minutes})

    m = _CRON_RE.match(raw)
    if m:
        return ("set_cron", {"cron_expr": m.group(1).strip()})

    if _IMMEDIATE_RE.match(raw):
        return ("set_immediate", {})

    if _SHOW_RE.match(raw):
        return ("show", {})

    if _TRIGGER_RE.match(raw):
        return ("trigger_now", {})

    return None


def parse_simple_cron_minutes(cron_expr: str) -> Optional[int]:
    """Support simple cron format: */N * * * *"""
    m = _SIMPLE_CRON_MIN_RE.match((cron_expr or "").strip())
    if not m:
        return None
    try:
        val = int(m.group(1))
        return val if val >= 1 else None
    except (TypeError, ValueError):
        return None


def should_auto_run_now(
    pref: Optional[DoctorNotifyPreference],
    now: datetime,
    *,
    include_manual: bool = False,
    force: bool = False,
) -> bool:
    if force:
        return True

    if pref is None:
        return True

    if pref.notify_mode == "manual" and not include_manual:
        return False

    schedule_type = pref.schedule_type or "immediate"
    last = pref.last_auto_run_at

    if schedule_type == "immediate":
        return True

    if schedule_type == "interval":
        minutes = max(1, int(pref.interval_minutes or 1))
        if last is None:
            return True
        return (now - last) >= timedelta(minutes=minutes)

    if schedule_type == "cron":
        every_minutes = parse_simple_cron_minutes(pref.cron_expr or "")
        if every_minutes is None:
            return True
        if last is None:
            return True
        return (now - last) >= timedelta(minutes=every_minutes)

    return True


def format_notify_pref(pref: Optional[DoctorNotifyPreference]) -> str:
    if pref is None:
        return (
            "⚙️ 通知设置\n"
            "模式：自动\n"
            "计划：实时\n"
            "最近调度：未执行"
        )

    mode_text = "自动" if pref.notify_mode == "auto" else "手动"
    schedule_type = pref.schedule_type or "immediate"
    if schedule_type == "interval":
        plan_text = "每{0}分钟检查".format(max(1, int(pref.interval_minutes or 1)))
    elif schedule_type == "cron":
        plan_text = "定时 {0}".format(pref.cron_expr or "(空)")
    else:
        plan_text = "实时"

    last = pref.last_auto_run_at
    if last is None:
        last_text = "未执行"
    else:
        dt = last.astimezone(timezone.utc)
        last_text = dt.strftime("%m-%d %H:%M")

    return (
        "⚙️ 通知设置\n"
        "模式：{0}\n"
        "计划：{1}\n"
        "最近调度：{2}"
    ).format(mode_text, plan_text, last_text)


async def get_notify_pref(doctor_id: str) -> Optional[DoctorNotifyPreference]:
    async with AsyncSessionLocal() as session:
        return await get_doctor_notify_preference(session, doctor_id)


async def set_notify_mode(doctor_id: str, notify_mode: str) -> DoctorNotifyPreference:
    async with AsyncSessionLocal() as session:
        return await upsert_doctor_notify_preference(session, doctor_id, notify_mode=notify_mode)


async def set_notify_interval(doctor_id: str, interval_minutes: int) -> DoctorNotifyPreference:
    minutes = max(1, int(interval_minutes))
    async with AsyncSessionLocal() as session:
        return await upsert_doctor_notify_preference(
            session,
            doctor_id,
            schedule_type="interval",
            interval_minutes=minutes,
            cron_expr=None,
        )


async def set_notify_cron(doctor_id: str, cron_expr: str) -> DoctorNotifyPreference:
    expr = (cron_expr or "").strip()
    if parse_simple_cron_minutes(expr) is None:
        raise ValueError("仅支持 cron 格式 */N * * * *（分钟粒度）")
    async with AsyncSessionLocal() as session:
        return await upsert_doctor_notify_preference(
            session,
            doctor_id,
            schedule_type="cron",
            cron_expr=expr,
        )


async def set_notify_immediate(doctor_id: str) -> DoctorNotifyPreference:
    async with AsyncSessionLocal() as session:
        return await upsert_doctor_notify_preference(
            session,
            doctor_id,
            schedule_type="immediate",
            interval_minutes=1,
            cron_expr=None,
        )
