"""
Shared query_records handler — channel-agnostic business logic.

Resolution order for patient scope:
  1. intent_result.patient_name  (explicit from user message)
  2. Session current_patient      (follow-up continuity)
  3. All records for doctor        (no patient scope)
"""
from __future__ import annotations

import asyncio
from typing import Optional

from db.crud import (
    find_patient_by_name,
    get_all_records_for_doctor,
    get_records_for_patient,
)
from db.engine import AsyncSessionLocal
from services.ai.intent import IntentResult
from services.domain.intent_handlers._types import HandlerResult
from services.observability.audit import audit
from services.observability.observability import get_current_trace_id, trace_block
from services.session import get_session, set_current_patient, set_patient_not_found
from utils.log import log


async def handle_query_records(
    doctor_id: str, intent_result: IntentResult,
) -> HandlerResult:
    """查询病历：按患者姓名、当前上下文或全量返回病历列表。"""
    name = intent_result.patient_name
    _prev: Optional[str] = None

    with trace_block("router", "records.chat.query_records", {"doctor_id": doctor_id, "patient_name": name, "intent": "query_records"}):
        async with AsyncSessionLocal() as db:
            # 1) Explicit patient name from user
            if name:
                patient = await find_patient_by_name(db, doctor_id, name)
                if not patient:
                    set_patient_not_found(doctor_id, name)
                    return HandlerResult(reply=f"未找到患者【{name}】。")
                _prev = set_current_patient(doctor_id, patient.id, patient.name)
                return await _query_patient_records(
                    db, doctor_id, patient.id, patient.name, _prev,
                )

            # 2) Session current_patient fallback (follow-up continuity)
            sess = get_session(doctor_id)
            if sess.current_patient_id:
                return await _query_patient_records(
                    db, doctor_id, sess.current_patient_id,
                    sess.current_patient_name, None,
                )

            # 3) All records for doctor
            records = await get_all_records_for_doctor(db, doctor_id)

    if not records:
        return HandlerResult(reply="📂 暂无任何病历记录。")
    lines = [f"📂 最近 {len(records)} 条记录："]
    for r in records:
        pname = r.patient.name if r.patient else "未关联"
        date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
        lines.append(f"【{pname}】[{date}] {(r.content or '—')[:60]}")
    asyncio.create_task(audit(
        doctor_id, "READ", resource_type="record",
        resource_id="all", trace_id=get_current_trace_id(),
    ))
    return HandlerResult(reply="\n".join(lines), records_list=list(records))


async def _query_patient_records(
    db, doctor_id: str, patient_id: int,
    patient_name: Optional[str], prev_patient: Optional[str],
) -> HandlerResult:
    """Fetch and format records for a single patient."""
    _switch = f"🔄 已从【{prev_patient}】切换到【{patient_name}】" if prev_patient else None
    records = await get_records_for_patient(db, doctor_id, patient_id)
    if not records:
        return HandlerResult(reply=f"📂 患者【{patient_name}】暂无历史记录。", switch_notification=_switch)
    lines = [f"📂 患者【{patient_name}】最近 {len(records)} 条记录："]
    for i, r in enumerate(records, 1):
        date = r.created_at.strftime("%Y-%m-%d") if r.created_at else "—"
        lines.append(f"{i}. [{date}] {(r.content or '—')[:60]}")
    asyncio.create_task(audit(
        doctor_id, "READ", resource_type="record",
        resource_id=patient_name or str(patient_id), trace_id=get_current_trace_id(),
    ))
    return HandlerResult(reply="\n".join(lines), records_list=list(records))
