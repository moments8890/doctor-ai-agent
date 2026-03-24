"""Handler for query_task intent — fetch tasks, compose LLM summary."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from agent.dispatcher import register
from agent.prompt_composer import compose_for_intent
from agent.types import IntentType, HandlerResult, TurnContext
from agent.llm import llm_call
from utils.log import log


@register(IntentType.query_task)
async def handle_query_task(ctx: TurnContext) -> HandlerResult:
    status_filter = ctx.routing.params.get("status")
    tasks = await _fetch_tasks(ctx.doctor_id, status_filter)

    if not tasks:
        return HandlerResult(reply="当前没有任务。")

    summary = await _compose_task_summary(ctx, tasks)
    return HandlerResult(reply=summary, data={"tasks": tasks})


async def _fetch_tasks(doctor_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    from db.crud.tasks import list_tasks as db_list_tasks
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        tasks = await db_list_tasks(session, doctor_id, status=status)
        return [
            {"id": t.id, "title": getattr(t, "title", None),
             "status": getattr(t, "status", None),
             "due_at": t.due_at.isoformat() if getattr(t, "due_at", None) else None}
            for t in tasks
        ]


async def _compose_task_summary(ctx: TurnContext, tasks: list) -> str:
    from domain.knowledge.doctor_knowledge import load_knowledge_by_categories
    from agent.prompt_config import INTENT_LAYERS

    tasks_text = json.dumps(tasks, ensure_ascii=False, indent=2)
    config = INTENT_LAYERS[IntentType.query_task]
    doctor_kb = await load_knowledge_by_categories(
        ctx.doctor_id, config.knowledge_categories, query=ctx.text,
    )
    messages = compose_for_intent(
        IntentType.query_task,
        doctor_id=ctx.doctor_id,
        doctor_knowledge=doctor_kb,
        patient_context=tasks_text,
        doctor_message=ctx.text,
    )

    try:
        return await llm_call(
            messages=messages,
            op_name="compose.query_task",
            temperature=0.3,
            max_tokens=800,
        )
    except Exception as exc:
        log(f"[compose] task summary failed: {exc}", level="warning")
        return f"共有 {len(tasks)} 个任务。"
