"""Interview turn handler — core loop (ADR 0016).

Re-exports all public symbols so existing imports continue to work unchanged.
"""
from __future__ import annotations

import asyncio as _asyncio_lock
import json
import os
from typing import Any, Dict, List, Optional

# Per-session lock to prevent concurrent interview_turn calls on the same session.
# Capped to avoid unbounded growth from abandoned sessions.
_session_locks: dict[str, "_asyncio_lock.Lock"] = {}
_SESSION_LOCK_CAP = 500


def get_session_lock(session_id: str) -> "_asyncio_lock.Lock":
    """Get or create the per-session asyncio.Lock."""
    if len(_session_locks) >= _SESSION_LOCK_CAP:
        # Evict oldest half (dict preserves insertion order in Python 3.7+)
        keys = list(_session_locks.keys())
        for k in keys[: len(keys) // 2]:
            _session_locks.pop(k, None)
    return _session_locks.setdefault(session_id, _asyncio_lock.Lock())


def release_session_lock(session_id: str) -> None:
    """Remove the session lock entry when a session is finalized."""
    _session_locks.pop(session_id, None)

from domain.patients.completeness import (
    check_completeness,
    get_completeness_state,
    merge_extracted,
    total_fields,
)
from db.models.interview_session import InterviewStatus
from domain.patients.interview_session import load_session, save_session
from domain.patients.interview_models import (
    MAX_TURNS,
    ExtractedClinicalFields,
    InterviewLLMResponse,
    InterviewResponse,
    FIELD_LABELS,
    FIELD_META,
    _FIELD_PRIORITY,
    _PATIENT_PHASES,
    _build_progress,
)
from domain.patients.interview_context import (
    _load_patient_info,
    _load_previous_history,
)
from utils.log import log

__all__ = [
    "MAX_TURNS",
    "ExtractedClinicalFields",
    "InterviewLLMResponse",
    "InterviewResponse",
    "FIELD_LABELS",
    "_build_progress",
    "interview_turn",
    "get_session_lock",
    "release_session_lock",
]


async def _call_interview_llm(
    conversation: List[Dict[str, str]],
    collected: Dict[str, str],
    patient_info: Dict[str, Any],
    previous_history: Optional[str] = None,
    mode: str = "patient",
    doctor_id: str = "",
    completeness_state: dict = None,
) -> Dict[str, Any]:
    """Call LLM with interview prompt. Returns parsed {reply, extracted}."""
    from agent.llm import structured_call
    from agent.prompt_composer import compose_for_intent
    from agent.types import IntentType

    missing = check_completeness(collected, mode=mode)
    missing_labels = [FIELD_LABELS.get(f, f) for f in missing]

    # Build compact flat-text context (no XML — saves ~770 chars vs XML format)
    state = completeness_state or get_completeness_state(collected, mode=mode)

    clean_collected = {k: v for k, v in collected.items() if not k.startswith("_")}
    can_str = "是" if state["can_complete"] else "否"

    # "待补充" with inline hints (top 3 recommended/optional fields)
    guide_parts = []
    for fk in (state["recommended_missing"] + state["optional_missing"])[:3]:
        meta = FIELD_META.get(fk)
        label = FIELD_LABELS.get(fk, fk)
        if meta:
            guide_parts.append(f'{label}({meta["hint"]},如"{meta["example"]}")')
        else:
            guide_parts.append(label)

    # Required missing (only when can_complete is False)
    req_parts = []
    if not state["can_complete"]:
        for fk in state["required_missing"]:
            meta = FIELD_META.get(fk)
            label = FIELD_LABELS.get(fk, fk)
            if meta:
                req_parts.append(f'{label}({meta["hint"]},如"{meta["example"]}")')
            else:
                req_parts.append(label)

    context_lines = [
        f"患者：{patient_info['name']}，{patient_info['gender']}，{patient_info['age']}岁",
        f"已收集：{json.dumps(clean_collected, ensure_ascii=False)}",
        f"可完成：{can_str}",
    ]
    if req_parts:
        context_lines.append(f"必填缺：{'｜'.join(req_parts)}")
    if guide_parts:
        context_lines.append(f"待补充：{'｜'.join(guide_parts)}")
    if previous_history:
        prev = previous_history.replace("\n", " ").strip()
        if len(prev) > 100:
            prev = prev[:100] + "..."
        context_lines.append(f"上次：{prev}")
    patient_context = "\n".join(context_lines)

    # Build conversation history as message dicts
    history = [
        {"role": turn.get("role", "user"), "content": turn.get("content", "")}
        for turn in conversation[-6:]
    ]

    # Composer handles everything: layers 1-5 → system, history, layer 6 → user
    # conversation_mode=True puts KB + context in system (not XML user message)
    if mode == "patient":
        from agent.prompt_composer import compose_for_patient_interview
        messages = await compose_for_patient_interview(
            doctor_id=doctor_id,
            patient_context=patient_context,
            doctor_message="",  # no new user message — history has all turns
            history=history,
        )
    else:
        messages = await compose_for_intent(
            IntentType.create_record,
            doctor_id=doctor_id,
            patient_context=patient_context,
            doctor_message="",  # no new user message — history has all turns
            history=history,
        )

    env_var = "CONVERSATION_LLM" if os.environ.get("CONVERSATION_LLM") else "ROUTING_LLM"

    result = await structured_call(
        response_model=InterviewLLMResponse,
        messages=messages,
        op_name=f"interview.{mode}",
        env_var=env_var,
        temperature=0.1,
        max_tokens=2048,
    )

    # Convert ExtractedClinicalFields to dict, keeping only non-None fields
    extracted_dict = {k: v for k, v in result.extracted.model_dump().items() if v is not None and v.strip()}

    # Separate patient metadata from clinical fields (metadata is not stored in collected)
    patient_name_extracted = extracted_dict.pop("patient_name", None)
    patient_gender_extracted = extracted_dict.pop("patient_gender", None)
    patient_age_extracted = extracted_dict.pop("patient_age", None)

    suggestions = [str(s) for s in result.suggestions if s][:4]
    return {
        "reply": result.reply,
        "extracted": extracted_dict,
        "patient_name": patient_name_extracted,
        "patient_gender": patient_gender_extracted,
        "patient_age": patient_age_extracted,
        "suggestions": suggestions,
    }


async def interview_turn(session_id: str, patient_text: str) -> InterviewResponse:
    """Process one patient message in the interview. Core loop."""
    async with get_session_lock(session_id):
        return await _interview_turn_inner(session_id, patient_text)


async def _interview_turn_inner(session_id: str, patient_text: str) -> InterviewResponse:
    """Inner implementation — always called under the session lock."""
    session = await load_session(session_id)
    if session is None:
        return InterviewResponse(
            reply="问诊会话不存在。", collected={},
            progress={"filled": 0, "total": total_fields()}, status="error",
        )
    mode = getattr(session, "mode", "patient")
    resumed_from_review = session.status == InterviewStatus.reviewing
    if session.status not in (InterviewStatus.interviewing, InterviewStatus.reviewing):
        return InterviewResponse(
            reply="该问诊已结束。", collected=session.collected,
            progress=_build_progress(session.collected, mode), status=session.status,
            ready_to_review=session.status == InterviewStatus.reviewing,
        )
    if session.status == InterviewStatus.reviewing:
        # Patient chose "继续补充" — reopen the same session for one more turn.
        session.status = InterviewStatus.interviewing

    from datetime import datetime, timezone
    session.conversation.append({
        "role": "user", "content": patient_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    session.turn_count += 1

    # Safety cap — transition to reviewing so patient can complete
    if session.turn_count >= MAX_TURNS:
        missing = check_completeness(session.collected, mode=mode)
        reply = "我们已经聊了很久了，让我整理一下已有的信息。"
        session.conversation.append({"role": "assistant", "content": reply})
        session.status = InterviewStatus.reviewing
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_build_progress(session.collected, mode), status=session.status,
            missing=missing,
            ready_to_review=True,
        )

    # Main LLM call (with retry for transient failures)
    import asyncio as _asyncio
    patient_info = await _load_patient_info(session.patient_id)
    previous_history = await _load_previous_history(session.patient_id, session.doctor_id)

    completeness_state = get_completeness_state(session.collected, mode=mode)

    llm_response = None
    last_error = None
    for attempt in range(3):
        try:
            llm_response = await _call_interview_llm(
                conversation=session.conversation,
                collected=session.collected,
                patient_info=patient_info,
                previous_history=previous_history,
                mode=session.mode,
                doctor_id=session.doctor_id,
                completeness_state=completeness_state,
            )
            break
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            log(f"[interview] LLM parse error (attempt {attempt+1}): {e}", level="warning")
            last_error = e
            break  # parse errors won't be fixed by retrying
        except Exception as e:
            log(f"[interview] LLM call failed (attempt {attempt+1}/3): {e}", level="warning")
            last_error = e
            if attempt < 2:
                await _asyncio.sleep(1.0 * (attempt + 1))  # 1s, 2s backoff

    if llm_response is None:
        if isinstance(last_error, (json.JSONDecodeError, KeyError, TypeError, ValueError)):
            reply = "抱歉，我没有理解，请再说一次。"
        else:
            log(f"[interview] LLM call failed after 3 attempts: {last_error}", level="error")
            reply = "系统暂时繁忙，请稍后再试。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_build_progress(session.collected, mode), status=session.status,
            ready_to_review=session.status == InterviewStatus.reviewing,
        )

    # Merge extracted fields (clinical only — patient metadata excluded by _call_interview_llm)
    merge_extracted(session.collected, llm_response["extracted"])

    # Store patient metadata in collected with underscore prefix (not clinical fields)
    for meta_key in ("patient_name", "patient_gender", "patient_age"):
        meta_val = llm_response.get(meta_key)
        if meta_val and not session.collected.get(f"_{meta_key}"):
            session.collected[f"_{meta_key}"] = meta_val

    missing = check_completeness(session.collected, mode=mode)

    reply = llm_response.get("reply", "请继续描述您的情况。" if mode == "patient" else "收到，已记录。")

    # Post-processing guard: if can_complete, soften any blocking language
    state = get_completeness_state(session.collected, mode=mode)
    if state["can_complete"] and any(kw in reply for kw in ("还需要", "必须", "还缺")):
        # Replace blocking language with permissive language
        import re
        reply = re.sub(r"还需要补充.+?[。；]?", "如方便可再补充", reply)
        reply = re.sub(r"必须.+?[。；]?", "", reply)
        reply = re.sub(r"还缺.+?[。；]?", "", reply)
        if not reply.strip():
            reply = "已记录。现在可以点击「完成」生成病历。"

    ready_to_review = state["can_complete"] if mode == "doctor" else len(missing) == 0
    if ready_to_review and mode == "patient":
        session.status = InterviewStatus.reviewing
        if not resumed_from_review:
            reply = "我已经整理好主要信息。请确认后提交给医生；如果还有补充，也可以继续补充。"

    session.conversation.append({"role": "assistant", "content": reply})
    await save_session(session)

    suggestions = llm_response.get("suggestions", [])

    return InterviewResponse(
        reply=reply, collected=session.collected,
        progress=_build_progress(session.collected, mode), status=session.status,
        missing=missing,
        suggestions=suggestions,
        ready_to_review=ready_to_review,
        patient_name=llm_response.get("patient_name"),
        patient_gender=llm_response.get("patient_gender"),
        patient_age=llm_response.get("patient_age"),
    )
