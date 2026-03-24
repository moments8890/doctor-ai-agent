"""Handler for create_task intent — extract params, save to DB."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from agent.dispatcher import register
from agent.tools.resolve import resolve
from agent.types import IntentType, HandlerResult, TurnContext
from utils.log import log


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
        try:
            due_at = datetime.fromisoformat(due_at_str)
        except ValueError:
            return {"status": "error", "message": f"日期格式无效：{due_at_str}"}

    async with AsyncSessionLocal() as session:
        task = await db_create_task(
            session, doctor_id=doctor_id, task_type="general",
            title=title, content=content, patient_id=patient_id, due_at=due_at,
        )
        return {"status": "ok", "task_id": task.id, "title": title}
