"""Handler for query_record intent — fetch records, compose LLM summary."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from agent.dispatcher import register
from agent.prompt_composer import compose_for_intent
from agent.types import IntentType, HandlerResult, TurnContext
from agent.tools.resolve import resolve
from agent.llm import llm_call
from utils.log import log

# SOAP fields to include in query results (from domain.records.schema)
_SOAP_FIELDS = (
    "department", "chief_complaint", "present_illness", "past_history",
    "allergy_history", "personal_history", "marital_reproductive",
    "family_history", "physical_exam", "specialist_exam", "auxiliary_exam",
    "diagnosis", "treatment_plan", "orders_followup",
    "final_diagnosis", "treatment_outcome", "key_symptoms", "status",
)


def _record_to_dict(r: Any, patient_name: Optional[str] = None) -> Dict[str, Any]:
    """Convert a MedicalRecordDB row to a dict with SOAP fields."""
    d: Dict[str, Any] = {
        "id": r.id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
    if patient_name:
        d["patient_name"] = patient_name
    # Include legacy content as fallback
    if r.content:
        d["content"] = r.content
    # Include non-None SOAP fields
    for field in _SOAP_FIELDS:
        val = getattr(r, field, None)
        if val is not None:
            d[field] = val
    return d


@register(IntentType.query_record)
async def handle_query_record(ctx: TurnContext) -> HandlerResult:
    patient_name = ctx.routing.patient_name
    limit = ctx.routing.params.get("limit", 5)

    if patient_name:
        resolved = await resolve(patient_name, ctx.doctor_id)
        if "status" in resolved:
            return HandlerResult(reply=resolved["message"])
        records = await _fetch_records(ctx.doctor_id, resolved["patient_id"], limit, patient_name=patient_name)
    else:
        records = await _fetch_recent_records(ctx.doctor_id, limit)

    summary = await _compose_summary(ctx, records, patient_name)
    return HandlerResult(reply=summary, data={"records": records})


async def _fetch_records(doctor_id: str, patient_id: int, limit: int = 5, *, patient_name: Optional[str] = None) -> List[Dict[str, Any]]:
    from db.crud.records import get_records_for_patient
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_records_for_patient(session, doctor_id, patient_id, limit=limit)
        return [_record_to_dict(r, patient_name=patient_name) for r in records]


async def _fetch_recent_records(doctor_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    from db.crud.records import get_all_records_for_doctor
    from db.engine import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        records = await get_all_records_for_doctor(session, doctor_id, limit=limit)
        return [_record_to_dict(r) for r in records]


async def _compose_summary(ctx: TurnContext, records: list, patient_name: Optional[str] = None) -> str:
    if not records:
        return f"{'没有找到' + patient_name + '的' if patient_name else '暂无'}病历记录。"

    from domain.knowledge.doctor_knowledge import load_knowledge_by_categories
    from agent.prompt_config import INTENT_LAYERS

    # Prepend patient context so the LLM knows whose records these are
    if patient_name:
        header = f"以下是{patient_name}的病历记录：\n"
    else:
        header = "以下是最近的病历记录：\n"
    records_text = header + json.dumps(records, ensure_ascii=False, indent=2)

    config = INTENT_LAYERS[IntentType.query_record]
    doctor_kb = await load_knowledge_by_categories(
        ctx.doctor_id, config.knowledge_categories, query=ctx.text,
    )
    messages = compose_for_intent(
        IntentType.query_record,
        doctor_id=ctx.doctor_id,
        doctor_knowledge=doctor_kb,
        patient_context=records_text,
        doctor_message=ctx.text,
    )

    try:
        return await llm_call(
            messages=messages,
            op_name="compose.query_record",
            temperature=0.3,
            max_tokens=800,
        )
    except Exception as exc:
        log(f"[compose] LLM failed, returning raw summary: {exc}", level="warning")
        return f"查询到 {len(records)} 条病历记录。"
