"""Interview turn handler — core loop (ADR 0016)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from services.ai.llm_client import _PROVIDERS
from services.patient_interview.completeness import (
    TOTAL_FIELDS,
    check_completeness,
    count_filled,
    merge_extracted,
)
from services.patient_interview.session import InterviewSession, load_session, save_session
from utils.log import log
from utils.prompt_loader import get_prompt_sync

MAX_TURNS = 30

_INTERVIEW_PROMPT: Optional[str] = None

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


def _get_prompt() -> str:
    global _INTERVIEW_PROMPT
    if _INTERVIEW_PROMPT is None:
        _INTERVIEW_PROMPT = get_prompt_sync("patient-interview")
    return _INTERVIEW_PROMPT


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


async def _call_interview_llm(
    conversation: List[Dict[str, str]],
    collected: Dict[str, str],
    patient_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Call LLM with interview prompt. Returns parsed {reply, extracted}."""
    missing = check_completeness(collected)
    missing_labels = [FIELD_LABELS.get(f, f) for f in missing]

    prompt_template = _get_prompt()
    system_prompt = (
        prompt_template
        .replace("{name}", patient_info["name"])
        .replace("{gender}", patient_info["gender"])
        .replace("{age}", str(patient_info["age"]))
        .replace("{collected_json}", json.dumps(collected, ensure_ascii=False, indent=2))
        .replace("{missing_fields}", "、".join(missing_labels) if missing_labels else "无（可进入确认）")
    )

    # Build messages: system + conversation history (capped at last 20 turns)
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in conversation[-20:]:
        messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

    provider_name = os.environ.get("CONVERSATION_LLM") or os.environ.get("ROUTING_LLM", "deepseek")
    provider = _PROVIDERS.get(provider_name)
    if provider is None:
        provider_name = "deepseek"
        provider = _PROVIDERS["deepseek"]

    extra_headers = {"anthropic-version": "2023-06-01"} if provider_name == "claude" else {}
    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
        timeout=float(os.environ.get("INTERVIEW_LLM_TIMEOUT", "30")),
        max_retries=0,
        default_headers=extra_headers,
    )

    model_name = provider.get("model", "deepseek-chat")
    _tag = f"[interview:{provider_name}:{model_name}]"
    log(f"{_tag} turn request")

    completion = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.3,
        response_format={"type": "json_object"},
        max_tokens=500,
    )

    raw = completion.choices[0].message.content or ""
    log(f"{_tag} response: {raw[:200]}")

    data = json.loads(raw)
    return {
        "reply": data.get("reply", "请继续描述您的情况。"),
        "extracted": data.get("extracted", {}),
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
    if session.status not in ("interviewing",):
        return InterviewResponse(
            reply="该问诊已结束。", collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )

    session.conversation.append({
        "role": "user", "content": patient_text,
        "timestamp": datetime.utcnow().isoformat(),
    })
    session.turn_count += 1

    # Force review if turn limit reached
    if session.turn_count >= MAX_TURNS:
        session.status = "reviewing"
        reply = "我已经收集了足够的信息，请查看摘要并确认提交。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_make_progress(session.collected), status=session.status,
        )

    # Main LLM call
    try:
        patient_info = await _load_patient_info(session.patient_id)
        llm_response = await _call_interview_llm(
            conversation=session.conversation,
            collected=session.collected,
            patient_info=patient_info,
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

    # Completeness check
    missing = check_completeness(session.collected)

    if not missing:
        session.status = "reviewing"
        reply = "信息收集完成！请点击右上角的摘要按钮，查看并确认提交给医生。"
    else:
        reply = llm_response["reply"]

    session.conversation.append({"role": "assistant", "content": reply})
    await save_session(session)

    return InterviewResponse(
        reply=reply, collected=session.collected,
        progress=_make_progress(session.collected), status=session.status,
    )
