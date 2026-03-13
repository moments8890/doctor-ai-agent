"""
Fast-path command handlers and notify control — live helpers used by routers.

Legacy per-intent handlers (handle_create_patient, handle_add_record, etc.)
have been removed.  All intent dispatch now goes through the 5-layer workflow
pipeline and ``services.domain.intent_handlers.dispatch_intent``.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from db.crud import (
    delete_patient_for_doctor,
    update_task_status,
)
from db.engine import AsyncSessionLocal
from db.models.medical_record import MedicalRecord
from services.notify.tasks import run_due_task_cycle
from services.notify.notify_control import (
    parse_notify_command,
    get_notify_pref,
    set_notify_mode,
    set_notify_interval,
    set_notify_cron,
    set_notify_immediate,
    format_notify_pref,
)
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id, trace_block
from utils.log import log, safe_create_task


# ---------------------------------------------------------------------------
# Internal response model used by fastpath helpers in this module.
#
# This mirrors routers.records.ChatResponse (the live API contract) but is
# defined here to avoid a circular import.  FastAPI serializes both
# identically.  Do NOT import this from outside — use the canonical
# ChatResponse in routers.records instead.
# ---------------------------------------------------------------------------

class ChatResponse(BaseModel):
    reply: str
    record: Optional[MedicalRecord] = None
    pending_id: Optional[str] = None
    pending_patient_name: Optional[str] = None
    pending_expires_at: Optional[str] = None  # ISO-8601 UTC


# ---------------------------------------------------------------------------
# Notify-control command handler
# ---------------------------------------------------------------------------

async def handle_notify_control_command(doctor_id: str, text: str) -> Optional[str]:
    """解析并执行通知控制命令，返回回复文本；无匹配返回 None。"""
    parsed = parse_notify_command(text)
    if not parsed:
        return None
    action, payload = parsed
    if action == "show":
        pref = await get_notify_pref(doctor_id)
        return format_notify_pref(pref)
    if action == "set_mode":
        pref = await set_notify_mode(doctor_id, payload["notify_mode"])
        mode_text = "自动" if pref.notify_mode == "auto" else "手动"
        return "✅ 通知模式已更新为：{0}".format(mode_text)
    if action == "set_interval":
        pref = await set_notify_interval(doctor_id, int(payload["interval_minutes"]))
        return "✅ 通知频率已更新：每{0}分钟自动检查".format(pref.interval_minutes)
    if action == "set_cron":
        try:
            pref = await set_notify_cron(doctor_id, str(payload["cron_expr"]))
            return "✅ 通知计划已更新：{0}".format(pref.cron_expr or "")
        except ValueError as e:
            return "⚠️ {0}".format(str(e))
    if action == "set_immediate":
        await set_notify_immediate(doctor_id)
        return "✅ 通知计划已更新为：实时检查"
    if action == "trigger_now":
        result = await run_due_task_cycle(doctor_id=doctor_id, include_manual=True, force=True)
        return (
            "✅ 已触发待办通知：due={0}, eligible={1}, sent={2}, failed={3}"
        ).format(
            result.get("due_count", 0), result.get("eligible_count", 0),
            result.get("sent_count", 0), result.get("failed_count", 0),
        )
    return None


# ---------------------------------------------------------------------------
# Fast-path command handlers
# ---------------------------------------------------------------------------

async def fastpath_complete_task(
    text: str, doctor_id: str, complete_re: "re.Pattern",
) -> Optional[ChatResponse]:
    """Intercept 完成 N before routing to skip LLM."""
    m = complete_re.match(text)
    if not m:
        return None
    task_id = int(m.group(1))
    with trace_block("router", "records.chat.complete_task.fastpath", {"doctor_id": doctor_id, "task_id": task_id}):
        async with AsyncSessionLocal() as db:
            task = await update_task_status(db, task_id, doctor_id, "completed")
    if task is None:
        return ChatResponse(reply=f"⚠️ 未找到任务 {task_id}，请确认编号是否正确。")
    return ChatResponse(reply=f"✅ 任务【{task.title}】已标记完成。")


async def fastpath_delete_patient_by_id(
    doctor_id: str, text: str, parse_fn: "callable",
) -> Optional[ChatResponse]:
    """快速路径：按 ID 删除患者；不匹配返回 None。"""
    delete_patient_id, _, _ = parse_fn(text)
    if delete_patient_id is None:
        return None
    with trace_block(
        "router", "records.chat.delete_patient_by_id.fastpath",
        {"doctor_id": doctor_id, "patient_id": delete_patient_id},
    ):
        async with AsyncSessionLocal() as db:
            deleted = await delete_patient_for_doctor(db, doctor_id, delete_patient_id)
    if deleted is None:
        return ChatResponse(reply=f"⚠️ 未找到患者 ID {delete_patient_id}。")
    safe_create_task(audit(
        doctor_id, "DELETE", resource_type="patient",
        resource_id=str(deleted.id), trace_id=get_current_trace_id(),
    ))
    return ChatResponse(reply=f"✅ 已删除患者【{deleted.name}】(ID {deleted.id}) 及其相关记录。")


async def fastpath_save_context(
    doctor_id: str, text: str, history: list, context_save_re: "re.Pattern",
    upsert_fn: "callable",
) -> Optional[ChatResponse]:
    """快速路径：保存医生上下文摘要；不匹配返回 None。"""
    context_match = context_save_re.match(text)
    if not context_match:
        return None
    explicit_summary = (context_match.group(1) or "").strip()
    if explicit_summary:
        summary = explicit_summary
    else:
        recent_user_msgs = [m["content"] for m in history if m.get("role") == "user"][-4:]
        summary = "；".join(msg.strip() for msg in recent_user_msgs if msg and msg.strip())[:200] or "暂无摘要"
    async with AsyncSessionLocal() as db:
        await upsert_fn(db, doctor_id, summary)
    return ChatResponse(reply=f"✅ 已保存医生上下文摘要：{summary}")
