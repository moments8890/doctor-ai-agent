"""Handler for query_record intent — fetch records, compose LLM summary."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext
from agent.tools.resolve import resolve
from utils.log import log
from utils.prompt_loader import get_prompt_sync


@register(IntentType.query_record)
async def handle_query_record(ctx: TurnContext) -> HandlerResult:
    patient_name = ctx.routing.patient_name
    limit = ctx.routing.params.get("limit", 5)

    if patient_name:
        resolved = await resolve(patient_name, ctx.doctor_id)
        if "status" in resolved:
            return HandlerResult(reply=resolved["message"])
        records = await _fetch_records(ctx.doctor_id, resolved["patient_id"], limit)
    else:
        records = await _fetch_recent_records(ctx.doctor_id, limit)

    summary = await _compose_summary(ctx.text, records, patient_name)
    return HandlerResult(reply=summary, data={"records": records})


async def _fetch_records(doctor_id: str, patient_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    from db.crud.records import get_records_for_patient
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_records_for_patient(session, doctor_id, patient_id, limit=limit)
        return [{"id": r.id, "content": r.content or "", "created_at": r.created_at.isoformat() if r.created_at else None} for r in records]


async def _fetch_recent_records(doctor_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    from db.crud.records import get_all_records_for_doctor
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_all_records_for_doctor(session, doctor_id, limit=limit)
        return [{"id": r.id, "content": r.content or "", "created_at": r.created_at.isoformat() if r.created_at else None} for r in records]


async def _compose_summary(query: str, records: list, patient_name: Optional[str] = None) -> str:
    if not records:
        return f"{'没有找到' + patient_name + '的' if patient_name else '暂无'}病历记录。"

    import json
    from agent.llm import llm_call

    compose_prompt = get_prompt_sync("compose")
    records_text = json.dumps(records, ensure_ascii=False, indent=2)

    try:
        return await llm_call(
            messages=[
                {"role": "system", "content": compose_prompt},
                {"role": "user", "content": f"医生查询：{query}\n\n数据：\n{records_text}"},
            ],
            op_name="compose.query_record",
            temperature=0.3,
            max_tokens=800,
        )
    except Exception as exc:
        log(f"[compose] LLM failed, returning raw summary: {exc}", level="warning")
        return f"查询到 {len(records)} 条病历记录。"
