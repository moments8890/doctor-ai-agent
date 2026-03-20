"""Diagnosis tools and case context injection for doctor chat."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool

from agent.identity import get_current_identity
from db.engine import AsyncSessionLocal
from db.crud.case_history import match_cases
from utils.log import log

_case_context_cache: Dict[str, Tuple[str, float]] = {}
_CACHE_TTL = 300  # 5 minutes


async def _build_case_context(doctor_id: str, chief_complaint: str) -> str:
    """Build case context string with 5-min TTL cache.

    Returns a formatted context block for system prompt injection, or empty
    string when no similar cases are found or the query text is empty.
    """
    if not chief_complaint or not chief_complaint.strip():
        return ""

    cache_key = f"{doctor_id}:{chief_complaint[:50]}"
    now = time.time()

    if cache_key in _case_context_cache:
        cached, ts = _case_context_cache[cache_key]
        if now - ts < _CACHE_TTL:
            return cached

    try:
        async with AsyncSessionLocal() as session:
            matched = await match_cases(
                session, doctor_id, chief_complaint, limit=2, threshold=0.5
            )

        if not matched:
            context = ""
        else:
            lines = [
                f"- {m['chief_complaint'][:30]} → {m['final_diagnosis']} ({m['similarity']:.0%})"
                for m in matched
            ]
            context = "【类似病例参考】\n" + "\n".join(lines)

        _case_context_cache[cache_key] = (context, now)
        return context

    except Exception as e:
        log(f"[case_context] failed: {e}", level="warning")
        return ""


# ── diagnose() tool ───────────────────────────────────────────────────


@tool
async def diagnose() -> str:
    """为当前患者生成AI鉴别诊断建议。基于病历或对话内容分析。"""
    doctor_id = get_current_identity()

    # 1. Try to find current patient's latest medical record.
    from db.models import MedicalRecordDB
    from sqlalchemy import select

    record_id: Optional[int] = None
    async with AsyncSessionLocal() as session:
        rec = (await session.execute(
            select(MedicalRecordDB)
            .where(MedicalRecordDB.doctor_id == doctor_id)
            .order_by(MedicalRecordDB.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if rec:
            record_id = rec.id

    # 2. If no record, fall back to scanning chat history
    #    (same pattern as _create_pending_record in agent/tools/doctor.py).
    clinical_text: Optional[str] = None
    if not record_id:
        from agent import session as _session_mod
        history = _session_mod.get_agent_history(doctor_id)
        messages: List[str] = [
            getattr(msg, "content", "") or ""
            for msg in history
            if getattr(msg, "content", "")
        ]
        if messages:
            clinical_text = "\n".join(messages[-10:])  # last 10 messages

    if not record_id and not clinical_text:
        return "请先选择患者或描述症状，我才能生成诊断建议。"

    # 3. Run the diagnosis pipeline.
    from domain.diagnosis import run_diagnosis
    try:
        result = await run_diagnosis(
            doctor_id=doctor_id,
            record_id=record_id,
            clinical_text=clinical_text,
        )
    except Exception as e:
        log(f"[diagnose] pipeline error: {e}", level="error")
        return f"诊断分析失败：{e}"

    if result.get("status") == "failed":
        return f"诊断分析未能完成：{result.get('error_message', '未知错误')}"

    # 4. Format the result as conversational Chinese text.
    return _format_diagnosis_reply(result)


def _format_diagnosis_reply(result: Dict[str, Any]) -> str:
    """Format DiagnosisOutput dict as conversational Chinese text."""
    parts: List[str] = []

    # Similar case references
    refs = result.get("case_references", [])
    if refs:
        parts.append("📋 **类似病例参考：**")
        for r in refs[:3]:
            parts.append(
                f"  - {r.get('chief_complaint', '')[:30]}"
                f" → {r.get('final_diagnosis', '?')}"
                f" ({r.get('similarity', 0):.0%})"
            )

    # Red flags — show before differentials (safety-critical)
    flags = result.get("red_flags", [])
    if flags:
        parts.append("\n⚠️ **危险信号：**")
        for f in flags:
            parts.append(f"  - {f}")

    # Differential diagnoses
    diffs = result.get("differentials", [])
    if diffs:
        parts.append("\n🔍 **鉴别诊断：**")
        for i, d in enumerate(diffs, 1):
            parts.append(
                f"  {i}. {d.get('condition', '?')}"
                f" ({d.get('confidence', '中')})"
                f" — {d.get('reasoning', '')}"
            )

    # Workup recommendations
    workup = result.get("workup", [])
    if workup:
        parts.append("\n🏥 **检查建议：**")
        for w in workup:
            parts.append(
                f"  - {w.get('test', '?')}"
                f" [{w.get('urgency', '常规')}]"
                f" — {w.get('rationale', '')}"
            )

    # Treatment directions
    treat = result.get("treatment", [])
    if treat:
        parts.append("\n💊 **治疗方向：**")
        for t in treat:
            parts.append(
                f"  - {t.get('drug_class', '?')}"
                f" ({t.get('intervention', '?')})"
                f" — {t.get('description', '')}"
            )

    parts.append("\n⚕️ AI建议仅供参考，最终诊断由医生决定。")
    return "\n".join(parts)
