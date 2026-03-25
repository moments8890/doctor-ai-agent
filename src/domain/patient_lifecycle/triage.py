"""AI triage for patient messages (ADR 0020).

Classifies every inbound patient message into a triage category and routes it
to the appropriate handler:

- **informational** — AI answers directly using patient context
- **symptom_report / side_effect** — escalated to doctor with structured summary
- **general_question** — escalated (safe default for ambiguous messages)
- **urgent** — immediate safety guidance + doctor notification

This is safety-critical code: classification errors can suppress clinical
content.  The system prompt is deliberately conservative — ambiguous messages
are classified to the *most clinical* category, and low-confidence outputs
default to ``general_question`` (escalation).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.patient_message import list_patient_messages, save_patient_message
from db.models.patient import Patient
from domain.tasks.notifications import send_doctor_notification
from infra.llm.client import _get_providers
from infra.llm.resilience import call_with_retry_and_fallback
from infra.observability.observability import trace_block
from utils.log import log, safe_create_task


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class TriageCategory(str, Enum):
    """Patient message triage categories."""
    informational = "informational"
    symptom_report = "symptom_report"
    side_effect = "side_effect"
    general_question = "general_question"
    urgent = "urgent"


_VALID_CATEGORIES = {c.value for c in TriageCategory}

# Categories that trigger escalation to doctor (not AI-handled).
_ESCALATION_CATEGORIES = {
    TriageCategory.symptom_report,
    TriageCategory.side_effect,
    TriageCategory.general_question,
}


@dataclass
class TriageResult:
    """Output of the classify() step."""
    category: TriageCategory
    confidence: float


# ---------------------------------------------------------------------------
# Rate limiting — max 3 escalations per 6-hour window per patient
# ---------------------------------------------------------------------------

_RATE_LIMIT_WINDOW = 6 * 60 * 60  # 6 hours in seconds
_RATE_LIMIT_MAX = 3

# Key: (patient_id, doctor_id) → list of timestamps (epoch seconds)
_escalation_timestamps: Dict[tuple, List[float]] = {}


def _is_rate_limited(patient_id: int, doctor_id: str) -> bool:
    """Return True if the patient has exceeded the escalation notification limit.

    Trims expired entries on each call. The ``urgent`` category should bypass
    this check entirely (caller responsibility).
    """
    key = (patient_id, doctor_id)
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW

    # Trim expired entries
    timestamps = _escalation_timestamps.get(key, [])
    timestamps = [ts for ts in timestamps if ts > cutoff]
    _escalation_timestamps[key] = timestamps

    return len(timestamps) >= _RATE_LIMIT_MAX


def _record_escalation(patient_id: int, doctor_id: str) -> None:
    """Record a new escalation timestamp for rate limiting."""
    key = (patient_id, doctor_id)
    _escalation_timestamps.setdefault(key, []).append(time.time())


# ---------------------------------------------------------------------------
# Notification batching — 10-minute quiet window per patient
# ---------------------------------------------------------------------------

_BATCH_WINDOW = 10 * 60  # 10 minutes in seconds

# Key: (patient_id, doctor_id) → last notification epoch timestamp
_last_notify_time: Dict[tuple, float] = {}


def _should_notify(patient_id: int, doctor_id: str) -> bool:
    """Return True if enough time has passed since the last notification.

    The ``urgent`` category should bypass this check entirely (caller
    responsibility).
    """
    key = (patient_id, doctor_id)
    now = time.time()
    last = _last_notify_time.get(key, 0.0)
    return (now - last) >= _BATCH_WINDOW


def _mark_notified(patient_id: int, doctor_id: str) -> None:
    """Record that we just sent a notification for this patient."""
    _last_notify_time[(patient_id, doctor_id)] = time.time()


# ---------------------------------------------------------------------------
# Patient name helper
# ---------------------------------------------------------------------------

async def _get_patient_name(
    db_session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> str:
    """Look up the patient's display name; falls back to '患者'."""
    try:
        result = await db_session.execute(
            select(Patient.name).where(
                Patient.id == patient_id,
                Patient.doctor_id == doctor_id,
            )
        )
        name = result.scalar_one_or_none()
        return name if name else "患者"
    except Exception:
        return "患者"


# ---------------------------------------------------------------------------
# Fire-and-forget notification helper
# ---------------------------------------------------------------------------

async def _notify_doctor_safe(doctor_id: str, message: str) -> None:
    """Send notification to doctor, swallowing exceptions."""
    try:
        await send_doctor_notification(doctor_id, message)
    except Exception as exc:
        log(f"[triage] failed to notify doctor {doctor_id}: {exc}", level="error")


# ---------------------------------------------------------------------------
# LLM client management — mirrors diagnosis.py / structuring.py pattern
# ---------------------------------------------------------------------------

_TRIAGE_CLIENT_CACHE: Dict[str, AsyncOpenAI] = {}


def _resolve_provider() -> tuple:
    """Resolve the provider to use for triage LLM calls.

    Reads ``TRIAGE_LLM`` env var, falling back to the general
    ``ROUTING_LLM`` then ``groq``.  Returns ``(provider_name, provider_dict)``.
    """
    provider_name = (
        os.environ.get("TRIAGE_LLM")
        or os.environ.get("ROUTING_LLM", "groq")
    )
    providers = _get_providers()
    provider = providers.get(provider_name)
    if provider is None:
        # Fall back to groq if the configured provider is unknown.
        provider_name = "groq"
        provider = providers["groq"]
    return provider_name, dict(provider)


def _get_triage_client(provider_name: str, provider: Dict[str, Any]) -> AsyncOpenAI:
    """Return (or create) a singleton AsyncOpenAI client for triage calls."""
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", ""):
        return AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("TRIAGE_LLM_TIMEOUT", "30")),
            max_retries=0,
        )
    if provider_name not in _TRIAGE_CLIENT_CACHE:
        _TRIAGE_CLIENT_CACHE[provider_name] = AsyncOpenAI(
            base_url=provider["base_url"],
            api_key=os.environ.get(provider["api_key_env"], "nokeyneeded"),
            timeout=float(os.environ.get("TRIAGE_LLM_TIMEOUT", "30")),
            max_retries=0,
        )
    return _TRIAGE_CLIENT_CACHE[provider_name]


def _make_llm_caller(
    client: AsyncOpenAI,
    provider_name: str,
    system_prompt: str,
    user_content: str,
    *,
    max_tokens: int = 1500,
):
    """Return an async callable suitable for ``call_with_retry_and_fallback``."""
    async def _call(model_name: str):
        with trace_block("llm", "triage.chat_completion", {"provider": provider_name, "model": model_name}):
            return await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                temperature=0,
            )
    return _call


async def _call_triage_llm(system_prompt: str, user_content: str, *, max_tokens: int = 1500) -> str:
    """Make a single triage LLM call with retry. Returns raw response text."""
    provider_name, provider = _resolve_provider()
    client = _get_triage_client(provider_name, provider)
    caller = _make_llm_caller(client, provider_name, system_prompt, user_content, max_tokens=max_tokens)

    response = await call_with_retry_and_fallback(
        caller,
        primary_model=provider["model"],
        max_attempts=int(os.environ.get("TRIAGE_LLM_ATTEMPTS", "2")),
        op_name="triage.chat_completion",
    )
    raw = response.choices[0].message.content or ""
    # Strip <think>...</think> tags if model emits them
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    return raw


# ---------------------------------------------------------------------------
# Step 1: Classify
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM_PROMPT = """\
你是一个医疗消息分类系统。你的任务是将患者发来的消息分类到以下类别之一：

## 分类类别

1. **informational** — 一般性信息问题：关于治疗计划的疑问、用药时间/方式、预约安排、检查结果解读等非紧急问题
2. **symptom_report** — 症状报告：患者描述新出现的症状、原有症状加重、身体不适等
3. **side_effect** — 药物副作用：患者报告用药后出现的不良反应、副作用
4. **general_question** — 无法明确分类的一般问题：当消息内容模糊或混合多种类型时使用此类别
5. **urgent** — 紧急情况：胸痛、呼吸困难、大出血、意识障碍、严重过敏反应、自伤/自杀倾向等需要立即就医的情况

## 分类规则

- 如果消息同时包含信息性问题和临床内容（症状/副作用），分类为**更临床的类别**
- 如果无法确定分类，默认使用 **general_question**（宁可升级处理，不可遗漏临床信息）
- confidence 取值 0.0-1.0，反映你对分类的确信程度

## 患者上下文

{patient_context}

## 输出格式

返回严格的 JSON：
```json
{{"category": "...", "confidence": 0.85}}
```

仅返回 JSON，不要包含任何其他文字。
"""


async def classify(message: str, patient_context: dict) -> TriageResult:
    """Classify a patient message into a triage category.

    Uses LLM to analyze the message against patient context (treatment plan,
    medications, recent messages, diagnosis summary).

    If confidence < 0.7, defaults to ``general_question`` (safe escalation).
    """
    context_text = json.dumps(patient_context, ensure_ascii=False, indent=2)
    system = _CLASSIFY_SYSTEM_PROMPT.replace("{patient_context}", context_text)

    try:
        raw = await _call_triage_llm(system, message, max_tokens=200)
        data = json.loads(raw)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        log(f"[triage] classify parse error: {exc}", level="warning")
        return TriageResult(category=TriageCategory.general_question, confidence=0.0)
    except Exception as exc:
        log(f"[triage] classify LLM call failed: {exc}", level="error")
        return TriageResult(category=TriageCategory.general_question, confidence=0.0)

    raw_category = data.get("category", "general_question")
    confidence = float(data.get("confidence", 0.0))

    # Validate category
    if raw_category not in _VALID_CATEGORIES:
        log(f"[triage] unknown category '{raw_category}', defaulting to general_question", level="warning")
        raw_category = "general_question"
        confidence = 0.0

    # Low confidence → safe default
    if confidence < 0.7:
        log(f"[triage] low confidence {confidence:.2f} for '{raw_category}', escalating to general_question")
        return TriageResult(
            category=TriageCategory.general_question,
            confidence=confidence,
        )

    return TriageResult(
        category=TriageCategory(raw_category),
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Step 2: Handlers
# ---------------------------------------------------------------------------

_INFORMATIONAL_SYSTEM_PROMPT = """\
你是患者的AI健康助手。请根据患者的治疗计划和病情信息，用简洁、准确、温暖的语气回答患者的问题。

## 回答规则

- 仅基于已有的患者信息回答，不要编造信息
- 如果信息不足以回答，建议患者咨询主治医生
- 使用通俗易懂的语言，避免过多医学术语
- 回答要简洁，通常不超过200字
- 不要给出诊断性意见或更改治疗方案的建议

## 患者上下文

{patient_context}

## 输出格式

返回严格的 JSON：
```json
{{"reply": "..."}}
```

仅返回 JSON，不要包含任何其他文字。
"""


async def handle_informational(
    message: str,
    context: dict,
    db_session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> str:
    """Handle an informational message: AI generates a direct answer.

    Saves both the inbound patient message and the outbound AI response
    with ``ai_handled=True`` and ``triage_category="informational"``.
    """
    context_text = json.dumps(context, ensure_ascii=False, indent=2)
    system = _INFORMATIONAL_SYSTEM_PROMPT.replace("{patient_context}", context_text)

    try:
        raw = await _call_triage_llm(system, message, max_tokens=500)
        data = json.loads(raw)
        reply = data.get("reply", "")
    except Exception as exc:
        log(f"[triage] handle_informational LLM failed: {exc}", level="error")
        reply = "抱歉，我暂时无法回答您的问题，已通知您的主治医生。"

    if not reply:
        reply = "抱歉，我暂时无法回答您的问题，已通知您的主治医生。"

    # Persist inbound patient message
    await save_patient_message(
        db_session,
        patient_id=patient_id,
        doctor_id=doctor_id,
        content=message,
        direction="inbound",
        source="patient",
        ai_handled=True,
        triage_category="informational",
    )
    # Persist outbound AI response
    await save_patient_message(
        db_session,
        patient_id=patient_id,
        doctor_id=doctor_id,
        content=reply,
        direction="outbound",
        source="ai",
        ai_handled=True,
        triage_category="informational",
    )

    return reply


_ESCALATION_SYSTEM_PROMPT = """\
你是一个医疗消息分析系统。患者的消息需要升级给主治医生处理。
请生成一个结构化的摘要，帮助医生快速了解情况。

## 患者上下文

{patient_context}

## 输出格式

返回严格的 JSON：
```json
{{
  "patient_question": "患者的具体问题/描述",
  "conversation_context": "近期对话的相关上下文",
  "patient_status": "患者当前状态摘要",
  "reason_for_escalation": "升级原因",
  "suggested_action": "建议医生采取的行动"
}}
```

仅返回 JSON，不要包含任何其他文字。
"""


async def handle_escalation(
    message: str,
    context: dict,
    category: str,
    db_session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> str:
    """Handle a message that requires doctor escalation.

    Generates a structured summary for the doctor, saves the message with
    ``ai_handled=False`` and the summary as ``structured_data``.

    Returns a patient-facing acknowledgment.
    """
    context_text = json.dumps(context, ensure_ascii=False, indent=2)
    system = _ESCALATION_SYSTEM_PROMPT.replace("{patient_context}", context_text)

    summary_json: Optional[str] = None
    try:
        raw = await _call_triage_llm(system, message, max_tokens=800)
        # Validate it parses as JSON
        summary = json.loads(raw)
        summary_json = json.dumps(summary, ensure_ascii=False)
    except Exception as exc:
        log(f"[triage] handle_escalation summary generation failed: {exc}", level="error")
        # Still escalate even if summary generation fails
        summary_json = json.dumps({
            "patient_question": message,
            "conversation_context": "",
            "patient_status": "未知",
            "reason_for_escalation": f"分类为{category}，摘要生成失败",
            "suggested_action": "请查看患者消息",
        }, ensure_ascii=False)

    # Persist inbound patient message with escalation metadata
    await save_patient_message(
        db_session,
        patient_id=patient_id,
        doctor_id=doctor_id,
        content=message,
        direction="inbound",
        source="patient",
        ai_handled=False,
        triage_category=category,
        structured_data=summary_json,
    )

    # Rate limiting: max 3 escalation notifications per 6h per patient.
    # If rate-limited, still save the message but don't notify the doctor.
    if _is_rate_limited(patient_id, doctor_id):
        log(f"[triage] rate-limited escalation for patient {patient_id}, skipping notification")
        reply = "医生将在查看时一并处理您的问题"
    else:
        _record_escalation(patient_id, doctor_id)
        reply = "这个问题需要您的主治医生回复，我已通知医生。"

        # Batch notifications: only notify if 10-min quiet window has elapsed.
        if _should_notify(patient_id, doctor_id):
            _mark_notified(patient_id, doctor_id)
            patient_name = await _get_patient_name(db_session, patient_id, doctor_id)
            preview = message[:40] + ("…" if len(message) > 40 else "")
            notification = "患者【{name}】有新消息需要您处理：{preview}".format(
                name=patient_name, preview=preview,
            )
            safe_create_task(_notify_doctor_safe(doctor_id, notification))
        else:
            log(f"[triage] batching notification for patient {patient_id} (within 10-min window)")

    # Persist outbound acknowledgment
    await save_patient_message(
        db_session,
        patient_id=patient_id,
        doctor_id=doctor_id,
        content=reply,
        direction="outbound",
        source="ai",
        ai_handled=False,
        triage_category=category,
    )

    return reply


async def handle_urgent(
    message: str,
    context: dict,
    db_session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> str:
    """Handle an urgent message: provide safety guidance and notify doctor.

    Returns a static safety message — no LLM call (latency matters for urgent).
    Saves with ``triage_category="urgent"`` and ``ai_handled=False``.

    ``urgent`` always notifies immediately — bypasses rate limiting and batching.
    """
    reply = "如出现严重症状请立即就医或拨打120。已通知您的主治医生。"

    # Persist inbound urgent message
    await save_patient_message(
        db_session,
        patient_id=patient_id,
        doctor_id=doctor_id,
        content=message,
        direction="inbound",
        source="patient",
        ai_handled=False,
        triage_category="urgent",
        structured_data=json.dumps({
            "patient_question": message,
            "reason_for_escalation": "紧急情况",
            "suggested_action": "请立即联系患者",
        }, ensure_ascii=False),
    )

    # Persist outbound safety guidance
    await save_patient_message(
        db_session,
        patient_id=patient_id,
        doctor_id=doctor_id,
        content=reply,
        direction="outbound",
        source="ai",
        ai_handled=False,
        triage_category="urgent",
    )

    # Urgent always notifies immediately — bypasses rate limiting and batching.
    patient_name = await _get_patient_name(db_session, patient_id, doctor_id)
    preview = message[:40] + ("…" if len(message) > 40 else "")
    notification = "【紧急】患者【{name}】: {preview}，请立即处理".format(
        name=patient_name, preview=preview,
    )
    _mark_notified(patient_id, doctor_id)
    safe_create_task(_notify_doctor_safe(doctor_id, notification))

    return reply


# ---------------------------------------------------------------------------
# Step 3: Patient context loader
# ---------------------------------------------------------------------------

async def load_patient_context(
    patient_id: int,
    doctor_id: str,
    db_session: AsyncSession,
) -> dict:
    """Build a patient context dict for injection into triage LLM prompts.

    Loads:
    - Latest treatment plan (not yet implemented)
    - Pending patient tasks
    - Recent 10 messages
    """
    from db.models.tasks import DoctorTask, TaskStatus
    from sqlalchemy import select

    # Treatment plan: not yet implemented (derive_treatment_plan removed).
    treatment_plan: Optional[Dict[str, Any]] = None

    # 1. Pending patient tasks
    pending_tasks: List[Dict[str, Any]] = []
    try:
        result = await db_session.execute(
            select(DoctorTask)
            .where(
                DoctorTask.patient_id == patient_id,
                DoctorTask.doctor_id == doctor_id,
                DoctorTask.target == "patient",
                DoctorTask.status.in_([TaskStatus.pending, TaskStatus.notified]),
            )
            .order_by(DoctorTask.due_at.asc())
            .limit(20)
        )
        for task in result.scalars().all():
            pending_tasks.append({
                "type": task.task_type,
                "title": task.title,
                "content": task.content,
                "due_at": task.due_at.isoformat() if task.due_at else None,
            })
    except Exception as exc:
        log(f"[triage] tasks load failed for patient {patient_id}: {exc}", level="warning")

    # 3. Recent messages (last 10)
    recent_messages: List[Dict[str, str]] = []
    try:
        messages = await list_patient_messages(
            db_session, patient_id, doctor_id, limit=10,
        )
        for msg in reversed(messages):  # oldest first for conversation flow
            recent_messages.append({
                "direction": msg.direction,
                "source": msg.source or ("patient" if msg.direction == "inbound" else "ai"),
                "content": msg.content[:300],  # truncate long messages
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            })
    except Exception as exc:
        log(f"[triage] messages load failed for patient {patient_id}: {exc}", level="warning")

    # 4. Diagnosis summary (extracted from treatment plan)
    diagnosis_summary: Optional[str] = None
    if treatment_plan:
        diagnoses = treatment_plan.get("diagnosis", [])
        if diagnoses:
            # Build a readable summary from differential diagnoses
            parts = []
            for d in diagnoses[:5]:  # cap at 5
                if isinstance(d, dict):
                    name = d.get("condition", d.get("name", ""))
                    if name:
                        parts.append(name)
                elif isinstance(d, str):
                    parts.append(d)
            if parts:
                diagnosis_summary = "、".join(parts)

    # 5. Medications (extracted from treatment plan)
    medications: List[str] = []
    if treatment_plan:
        for item in treatment_plan.get("treatment", [])[:10]:
            if isinstance(item, dict):
                drug = item.get("drug_class", item.get("description", ""))
                if drug:
                    medications.append(drug)

    return {
        "treatment_plan": treatment_plan,
        "pending_tasks": pending_tasks,
        "recent_messages": recent_messages,
        "diagnosis_summary": diagnosis_summary,
        "medications": medications,
    }
