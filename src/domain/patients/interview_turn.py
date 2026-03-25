"""Interview turn handler — core loop (ADR 0016)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from domain.patients.completeness import (
    check_completeness,
    count_filled,
    merge_extracted,
    total_fields,
)
from db.models.interview_session import InterviewStatus
from domain.patients.interview_session import InterviewSession, load_session, save_session
from utils.log import log
from utils.prompt_loader import get_prompt_sync

MAX_TURNS = 30


class ExtractedSOAPFields(BaseModel):
    """SOAP fields extracted from this turn. Only include fields with NEW information."""
    chief_complaint: Optional[str] = Field(None, description="主诉：主要症状+持续时间")
    present_illness: Optional[str] = Field(None, description="现病史：症状详情、检查结果、用药")
    past_history: Optional[str] = Field(None, description="既往史：既往疾病、手术")
    allergy_history: Optional[str] = Field(None, description="过敏史（无过敏填'无'）")
    family_history: Optional[str] = Field(None, description="家族史（无填'无'）")
    personal_history: Optional[str] = Field(None, description="个人史：吸烟、饮酒")
    marital_reproductive: Optional[str] = Field(None, description="婚育史")
    physical_exam: Optional[str] = Field(None, description="体格检查")
    specialist_exam: Optional[str] = Field(None, description="专科检查")
    auxiliary_exam: Optional[str] = Field(None, description="辅助检查：化验、影像")
    diagnosis: Optional[str] = Field(None, description="诊断")
    treatment_plan: Optional[str] = Field(None, description="治疗方案")
    orders_followup: Optional[str] = Field(None, description="医嘱及随访")


class InterviewLLMResponse(BaseModel):
    """Structured response from the interview LLM."""

    reply: str = Field(
        default="请继续描述您的情况。",
        description="给患者的自然语言回复（先回应，再提问）",
    )
    extracted: ExtractedSOAPFields = Field(
        default_factory=ExtractedSOAPFields,
        description="本轮新提取的SOAP字段（只填有新信息的字段，其余留null）",
    )
    suggestions: List[str] = Field(
        default_factory=list, description="建议的快捷回复选项"
    )

FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "family_history": "家族史",
    "personal_history": "个人史",
    "marital_reproductive": "婚育史",
    "physical_exam": "体格检查",
    "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查",
    "diagnosis": "诊断",
    "treatment_plan": "治疗方案",
    "orders_followup": "医嘱及随访",
}


# NHC Article 13 outpatient field priorities
_FIELD_PRIORITY = {
    "chief_complaint": "required",
    "present_illness": "required",
    "past_history": "recommended",
    "allergy_history": "recommended",
    "family_history": "recommended",
    "personal_history": "recommended",
    "marital_reproductive": "optional",
    "physical_exam": "recommended",
    "specialist_exam": "optional",
    "auxiliary_exam": "optional",
    "diagnosis": "recommended",
    "treatment_plan": "recommended",
    "orders_followup": "optional",
}

_PATIENT_PHASES = [
    ("主诉与现病史", ["chief_complaint", "present_illness"]),
    ("病史采集", ["past_history", "allergy_history", "family_history", "personal_history"]),
    ("补充信息", ["marital_reproductive"]),
]


def _build_progress(collected: Dict[str, str], mode: str = "patient") -> dict:
    """Build structured progress metadata for UI rendering."""
    _PATIENT_FIELDS = {
        "chief_complaint", "present_illness", "past_history",
        "allergy_history", "family_history", "personal_history", "marital_reproductive",
    }
    fields = {}
    for key, priority in _FIELD_PRIORITY.items():
        # Patient mode: only show the 7 subjective fields
        if mode == "patient" and key not in _PATIENT_FIELDS:
            continue
        fields[key] = {
            "status": "filled" if collected.get(key) else "empty",
            "priority": priority,
            "label": FIELD_LABELS.get(key, key),
        }

    filled = sum(1 for f in fields.values() if f["status"] == "filled")
    total = len(fields)
    pct = int(round(filled / total * 100)) if total else 0

    # Determine current phase (patient mode only)
    phase = "完成"
    if mode == "patient":
        for phase_name, phase_fields in _PATIENT_PHASES:
            if any(not collected.get(f) for f in phase_fields):
                phase = phase_name
                break

    return {
        "filled": filled,
        "total": total,
        "pct": pct,
        "phase": phase,
        "fields": fields,
    }


@dataclass
class InterviewResponse:
    reply: str
    collected: Dict[str, str]
    progress: dict  # structured progress with fields, pct, phase
    status: str
    missing: List[str] = None
    suggestions: List[str] = None


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

    # Try SOAP columns first, fall back to content
    if not row.has_soap_data():
        if row.content:
            # No structured data — include raw content as context (truncated)
            date_str = row.created_at.strftime("%Y-%m-%d") if row.created_at else "未知"
            content_preview = row.content[:500]
            return f"上次就诊（{date_str}）：\n{content_preview}"
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
        val = getattr(row, key, None) or ""
        if val and val not in ("无", "不详"):
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
    doctor_id: str = "",
) -> Dict[str, Any]:
    """Call LLM with interview prompt. Returns parsed {reply, extracted}."""
    from agent.llm import structured_call
    from agent.prompt_composer import compose_for_intent
    from agent.types import IntentType

    missing = check_completeness(collected, mode=mode)
    missing_labels = [FIELD_LABELS.get(f, f) for f in missing]

    # Build patient context (Layer 5 — goes into system for conversation_mode)
    context_lines = [
        f"患者信息：{patient_info['name']}，{patient_info['gender']}，{patient_info['age']}岁",
        f"已收集：{json.dumps(collected, ensure_ascii=False)}",
        f"待收集：{'、'.join(missing_labels) if missing_labels else '无（可进入确认）'}",
    ]
    if previous_history:
        context_lines.append(f"既往就诊记录：{previous_history}")
    patient_context = "\n".join(context_lines)

    # Build conversation history as message dicts
    history = [
        {"role": turn.get("role", "user"), "content": turn.get("content", "")}
        for turn in conversation[-20:]
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
        max_tokens=512,
    )

    # Convert ExtractedSOAPFields to dict, keeping only non-None fields
    extracted_dict = {k: v for k, v in result.extracted.model_dump().items() if v is not None and v.strip()}
    suggestions = [str(s) for s in result.suggestions if s][:4]
    return {
        "reply": result.reply,
        "extracted": extracted_dict,
        "suggestions": suggestions,
    }






async def interview_turn(session_id: str, patient_text: str) -> InterviewResponse:
    """Process one patient message in the interview. Core loop."""
    session = await load_session(session_id)
    if session is None:
        return InterviewResponse(
            reply="问诊会话不存在。", collected={},
            progress={"filled": 0, "total": total_fields()}, status="error",
        )
    mode = getattr(session, "mode", "patient")
    if session.status not in (InterviewStatus.interviewing,):
        return InterviewResponse(
            reply="该问诊已结束。", collected=session.collected,
            progress=_build_progress(session.collected, mode), status=session.status,
        )

    session.conversation.append({
        "role": "user", "content": patient_text,
        "timestamp": datetime.utcnow().isoformat(),
    })
    session.turn_count += 1

    # Safety cap — still process but flag it
    if session.turn_count >= MAX_TURNS:
        missing = check_completeness(session.collected, mode=mode)
        reply = "我们已经聊了很久了，让我整理一下已有的信息。"
        session.conversation.append({"role": "assistant", "content": reply})
        await save_session(session)
        return InterviewResponse(
            reply=reply, collected=session.collected,
            progress=_build_progress(session.collected, mode), status=session.status,
            missing=missing,
        )

    # Main LLM call (with retry for transient failures)
    import asyncio as _asyncio
    patient_info = await _load_patient_info(session.patient_id)
    previous_history = await _load_previous_history(session.patient_id, session.doctor_id)

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
        )

    # Merge extracted fields
    merge_extracted(session.collected, llm_response["extracted"])

    missing = check_completeness(session.collected, mode=mode)

    # Patient mode: use LLM's natural reply (conversational, asks follow-up questions)
    # Doctor mode: short acknowledgment (progress shown in UI, not in chat)
    if mode == "patient":
        reply = llm_response.get("reply", "请继续描述您的情况。")
    else:
        reply = "收到，已记录。"

    session.conversation.append({"role": "assistant", "content": reply})
    await save_session(session)

    return InterviewResponse(
        reply=reply, collected=session.collected,
        progress=_build_progress(session.collected, mode), status=session.status,
        missing=missing,
        suggestions=llm_response.get("suggestions", []),
    )
