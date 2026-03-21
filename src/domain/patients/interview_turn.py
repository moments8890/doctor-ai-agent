"""Interview turn handler — core loop (ADR 0016)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from domain.patients.completeness import (
    TOTAL_FIELDS,
    check_completeness,
    count_filled,
    merge_extracted,
)
from db.models.interview_session import InterviewStatus
from domain.patients.interview_session import InterviewSession, load_session, save_session
from utils.log import log
from utils.prompt_loader import get_prompt_sync

MAX_TURNS = 30

FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "family_history": "家族史",
    "personal_history": "个人史",
    "marital_reproductive": "婚育史",
}


@dataclass
class InterviewResponse:
    reply: str
    collected: Dict[str, str]
    progress: Dict[str, int]
    status: str
    missing: List[str] = None  # missing field names, empty = all collected
    suggestions: List[str] = None  # quick-reply options for the patient


def _get_prompt(mode: str = "patient") -> str:
    prompt_name = "doctor-interview" if mode == "doctor" else "patient-interview"
    return get_prompt_sync(prompt_name)


async def _load_patient_info(patient_id: int) -> Dict[str, Any]:
    """Load patient demographics for prompt context."""
    from db.engine import AsyncSessionLocal
    from db.models import Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        patient = (await db.execute(
            select(Patient).where(Patient.id == patient_id)
        )).scalar_one_or_none()

    if patient is None:
        return {"name": "未知", "gender": "未知", "age": "未知"}

    age = "未知"
    if patient.year_of_birth:
        age = str(datetime.now().year - patient.year_of_birth)

    return {
        "name": patient.name or "未知",
        "gender": patient.gender or "未知",
        "age": age,
    }


async def _load_previous_history(patient_id: int, doctor_id: str) -> Optional[str]:
    """Load structured fields from patient's latest record (if any) for context."""
    from db.engine import AsyncSessionLocal
    from db.models import MedicalRecordDB
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(MedicalRecordDB).where(
                MedicalRecordDB.patient_id == patient_id,
                MedicalRecordDB.doctor_id == doctor_id,
            ).order_by(MedicalRecordDB.created_at.desc()).limit(1)
        )).scalar_one_or_none()

    if row is None:
        return None

    # Try structured first, fall back to content
    structured = None
    if row.structured:
        try:
            structured = json.loads(row.structured)
        except (json.JSONDecodeError, TypeError):
            pass

    if not structured and row.content:
        # No structured data — include raw content as context (truncated)
        date_str = row.created_at.strftime("%Y-%m-%d") if row.created_at else "未知"
        content_preview = row.content[:500]
        return f"上次就诊（{date_str}）：\n{content_preview}"

    if not structured:
        return None

    # Build a readable summary of prior history fields
    history_fields = {
        "past_history": "既往史",
        "allergy_history": "过敏史",
        "family_history": "家族史",
        "personal_history": "个人史",
        "chief_complaint": "上次主诉",
        "diagnosis": "上次诊断",
    }
    lines = []
    for key, label in history_fields.items():
        val = structured.get(key, "")
        if val and val not in ("无", "不详", ""):
            lines.append(f"- {label}：{val}")

    if not lines:
        return None

    date_str = row.created_at.strftime("%Y-%m-%d") if row.created_at else "未知"
    return f"上次就诊（{date_str}）：\n" + "\n".join(lines)


async def _call_interview_llm(
    conversation: List[Dict[str, str]],
    collected: Dict[str, str],
    patient_info: Dict[str, Any],
    previous_history: Optional[str] = None,
    mode: str = "patient",
) -> Dict[str, Any]:
    """Call LLM with interview prompt. Returns parsed {reply, extracted}."""
    missing = check_completeness(collected)
    missing_labels = [FIELD_LABELS.get(f, f) for f in missing]

    prompt_template = _get_prompt(mode)
    system_prompt = (
        prompt_template
        .replace("{name}", patient_info["name"])
        .replace("{gender}", patient_info["gender"])
        .replace("{age}", str(patient_info["age"]))
        .replace("{collected_json}", json.dumps(collected, ensure_ascii=False, indent=2))
        .replace("{missing_fields}", "、".join(missing_labels) if missing_labels else "无（可进入确认）")
        .replace("{previous_history}", previous_history or "无")
    )

    # Build messages: system + conversation history (capped at last 20 turns)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in conversation[-20:]:
        messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

    # Use the same LangChain LLM as the agent.
    # Inject /no_think into system prompt to disable Qwen3 thinking mode —
    # the interview engine expects clean JSON, not <think> blocks.
    from agent.setup import get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = get_llm()
    _tag = f"[interview:{type(llm).__name__}]"
    log(f"{_tag} turn request")

    lc_messages = []
    for m in messages:
        if m["role"] == "system":
            lc_messages.append(SystemMessage(content=m["content"]))
        else:
            lc_messages.append(HumanMessage(content=m["content"]))

    response = await llm.ainvoke(lc_messages)
    raw = response.content or ""
    log(f"{_tag} response: {raw[:200]}")

    # Strip <think>...</think> tags if any still slip through
    import re as _re
    raw = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL).strip()

    data = json.loads(raw)
    suggestions = data.get("suggestions", [])
    if not isinstance(suggestions, list):
        suggestions = []
    suggestions = [str(s) for s in suggestions if s][:4]
    return {
        "suggested_reply": data.get("reply") or data.get("suggested_reply", "请继续描述您的情况。"),
        "extracted": data.get("extracted", {}),
        "suggestions": suggestions,
    }


def _make_progress(collected: Dict[str, str]) -> Dict[str, int]:
    return {"filled": count_filled(collected), "total": TOTAL_FIELDS}


async def interview_turn(session_id: str, patient_text: str) -> InterviewResponse:
    """Process one patient message in the interview. Core loop."""
    session = await load_session(session_id)
    if session is None:
        return InterviewResponse(
            reply="问诊会话不存在。", collected={},
            progress={"filled": 0, "total": TOTAL_FIELDS}, status="error",
        )
    if session.status not in (InterviewStatus.interviewing,):
        return InterviewResponse(
            reply="该问诊已结束。", collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )

    session.conversation.append({
        "role": "user", "content": patient_text,
        "timestamp": datetime.utcnow().isoformat(),
    })
    session.turn_count += 1

    # Safety cap — still process but flag it
    if session.turn_count >= MAX_TURNS:
        missing = check_completeness(session.collected)
        reply = "我们已经聊了很久了，让我整理一下已有的信息。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
            missing=missing,
        )

    # Main LLM call
    try:
        patient_info = await _load_patient_info(session.patient_id)
        previous_history = await _load_previous_history(session.patient_id, session.doctor_id)
        llm_response = await _call_interview_llm(
            conversation=session.conversation,
            collected=session.collected,
            patient_info=patient_info,
            previous_history=previous_history,
            mode=session.mode,
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        log(f"[interview] LLM parse error: {e}", level="warning")
        reply = "抱歉，我没有理解，请再说一次。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )
    except Exception as e:
        log(f"[interview] LLM call failed: {e}", level="error")
        reply = "系统暂时繁忙，请稍后再试。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )

    # Merge extracted fields
    merge_extracted(session.collected, llm_response["extracted"])

    # Report what's missing — agent decides when to close
    missing = check_completeness(session.collected)
    reply = llm_response["suggested_reply"]

    session.conversation.append({"role": "assistant", "content": reply})
    await save_session(session)

    return InterviewResponse(
        reply=reply, collected=session.collected,
        progress=_make_progress(session.collected), status=session.status,
        missing=missing,
        suggestions=llm_response.get("suggestions", []),
    )
