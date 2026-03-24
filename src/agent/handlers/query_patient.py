"""Handler for query_patient intent — search patients, compose summary."""
from __future__ import annotations

from agent.dispatcher import register
from agent.types import IntentType, HandlerResult, TurnContext


@register(IntentType.query_patient)
async def handle_query_patient(ctx: TurnContext) -> HandlerResult:
    query = ctx.routing.params.get("query", ctx.text)

    from domain.patients.nl_search import extract_criteria
    from db.crud.patient import get_all_patients
    from db.engine import AsyncSessionLocal
    from datetime import datetime

    criteria = extract_criteria(query)

    async with AsyncSessionLocal() as session:
        all_patients = await get_all_patients(session, ctx.doctor_id)

    results = []
    for p in all_patients:
        if criteria.surname and criteria.surname not in (p.name or ""):
            continue
        if criteria.gender and criteria.gender != getattr(p, "gender", None):
            continue
        if criteria.age_min and getattr(p, "year_of_birth", None):
            age = datetime.now().year - p.year_of_birth
            if age < criteria.age_min:
                continue
        if criteria.age_max and getattr(p, "year_of_birth", None):
            age = datetime.now().year - p.year_of_birth
            if age > criteria.age_max:
                continue
        results.append({"id": p.id, "name": p.name, "gender": getattr(p, "gender", None)})

    if not results:
        return HandlerResult(reply="没有找到符合条件的患者。")

    names = "、".join(p["name"] for p in results[:10])
    return HandlerResult(
        reply=f"找到 {len(results)} 位患者：{names}",
        data={"patients": results},
    )
