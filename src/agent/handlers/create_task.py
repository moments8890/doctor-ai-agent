"""Handler for create_task intent — extract params, save to DB."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from agent.dispatcher import register
from agent.tools.resolve import resolve
from agent.types import IntentType, HandlerResult, TurnContext
from utils.log import log


_WEEKDAY_ZH = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_NEXT_WEEK_RE = re.compile(r"下周([一二三四五六日天])")


def _parse_chinese_date(raw: str) -> Optional[datetime]:
    """Best-effort parse of Chinese relative date expressions.

    Handles: 明天, 后天, 下周X, 下个月, with optional 上午/下午/晚上 time.
    Returns None if unparseable.
    """
    now = datetime.now()
    base: Optional[datetime] = None
    text = raw.strip()

    # Absolute ISO-8601 — try first
    try:
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        pass

    # 今天
    if text.startswith("今天"):
        base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # 明天
    elif text.startswith("明天"):
        base = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    # 后天
    elif text.startswith("后天"):
        base = (now + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    # 下周X — always targets next calendar week (7–13 days ahead)
    else:
        m = _NEXT_WEEK_RE.match(text)
        if m:
            target_wd = _WEEKDAY_ZH.get(m.group(1))
            if target_wd is not None:
                days_to_next = (target_wd - now.weekday() + 7) % 7 or 7
                days_ahead = days_to_next + 7  # ensure next week, not this week
                base = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    # 下个月
    if base is None and text.startswith("下个月"):
        month = now.month + 1
        year = now.year + (1 if month > 12 else 0)
        month = month if month <= 12 else month - 12
        base = now.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)

    if base is None:
        return None

    # Apply time-of-day suffix
    if "下午" in text:
        base = base.replace(hour=14)
    elif "上午" in text:
        base = base.replace(hour=9)
    elif "晚上" in text:
        base = base.replace(hour=20)

    return base


@register(IntentType.create_task)
async def handle_create_task(ctx: TurnContext) -> HandlerResult:
    title = ctx.routing.params.get("title")
    if not title:
        return HandlerResult(reply='请提供任务标题，例如"建个复查血常规的任务"。')

    result = await _resolve_and_save_task(
        doctor_id=ctx.doctor_id,
        patient_name=ctx.routing.patient_name,
        title=title,
        content=ctx.routing.params.get("content"),
        due_at_str=ctx.routing.params.get("due_at"),
    )

    if result.get("status") == "error":
        return HandlerResult(reply=result["message"])

    reply = f"已创建任务：{result['title']}"
    if result.get("task_id"):
        reply += f"（#{result['task_id']}）"
    return HandlerResult(reply=reply, data=result)


async def _resolve_and_save_task(
    doctor_id: str, patient_name: Optional[str],
    title: str, content: Optional[str] = None,
    due_at_str: Optional[str] = None,
) -> Dict[str, Any]:
    from db.crud.tasks import create_task as db_create_task
    from db.engine import AsyncSessionLocal

    patient_id = None
    if patient_name:
        resolved = await resolve(patient_name, doctor_id)
        if "status" in resolved:
            return resolved
        patient_id = resolved["patient_id"]

    due_at = None
    if due_at_str:
        due_at = _parse_chinese_date(due_at_str)
        if due_at is None:
            log(f"[create_task] unparseable due_at '{due_at_str}', creating task without deadline")
            # Append the raw date text to content so it's not lost
            if content:
                content = f"{content}（{due_at_str}）"
            else:
                content = due_at_str

    async with AsyncSessionLocal() as session:
        task = await db_create_task(
            session, doctor_id=doctor_id, task_type="general",
            title=title, content=content, patient_id=patient_id, due_at=due_at,
        )
        return {"status": "ok", "task_id": task.id, "title": title}
