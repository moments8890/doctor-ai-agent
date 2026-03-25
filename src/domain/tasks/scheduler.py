"""
通知偏好管理：解析医生的免打扰时段设置，控制通知发送时机。

DoctorNotifyPreference table has been removed. Notification scheduling
now always uses "auto / immediate" defaults. The parse/format helpers
remain for command compatibility but no longer persist to DB.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple, Dict, Any


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
    pref: Optional[Any] = None,
    now: Optional[datetime] = None,
    *,
    include_manual: bool = False,
    force: bool = False,
) -> bool:
    """Always returns True — DoctorNotifyPreference table removed."""
    return True


def format_notify_pref(pref: Optional[Any] = None) -> str:
    """Return default notification settings display."""
    return (
        "\u2699\ufe0f 通知设置\n"
        "模式：自动\n"
        "计划：实时\n"
        "最近调度：未执行"
    )


async def get_notify_pref(doctor_id: str) -> None:
    """No-op — DoctorNotifyPreference table removed."""
    return None


async def set_notify_mode(doctor_id: str, notify_mode: str) -> None:
    """No-op — DoctorNotifyPreference table removed."""
    return None


async def set_notify_interval(doctor_id: str, interval_minutes: int) -> None:
    """No-op — DoctorNotifyPreference table removed."""
    return None


async def set_notify_cron(doctor_id: str, cron_expr: str) -> None:
    """No-op — DoctorNotifyPreference table removed."""
    return None


async def set_notify_immediate(doctor_id: str) -> None:
    """No-op — DoctorNotifyPreference table removed."""
    return None
