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
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.patient_message import list_patient_messages, save_patient_message
from db.models.patient import Patient
from domain.tasks.notifications import send_doctor_notification
from utils.log import log, safe_create_task
from utils.prompt_loader import get_prompt_sync


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


# -- Pydantic response models for structured_call() -----------------------

class ClassifyLLMResponse(BaseModel):
    """LLM response for triage classification."""
    category: TriageCategory
    confidence: float = Field(ge=0.0, le=1.0)


class InformationalLLMResponse(BaseModel):
    """LLM response for informational patient questions."""
    reply: str


class EscalationLLMResponse(BaseModel):
    """LLM response for escalation summary."""
    patient_question: str
    conversation_context: str
    patient_status: str
    reason_for_escalation: str
    suggested_action: str


def _triage_env_var() -> str:
    """Resolve env var for triage LLM: TRIAGE_LLM → ROUTING_LLM → groq."""
    if os.environ.get("TRIAGE_LLM"):
        return "TRIAGE_LLM"
    return "ROUTING_LLM"


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
# Step 1: Classify
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM_PROMPT = get_prompt_sync("intent/triage-classify")


async def classify(message: str, patient_context: dict) -> TriageResult:
    """Classify a patient message into a triage category.

    Uses structured_call() with ClassifyLLMResponse for validated output.
    If confidence < 0.7, defaults to ``general_question`` (safe escalation).
    """
    from agent.llm import structured_call

    context_text = json.dumps(patient_context, ensure_ascii=False, indent=2)
    system = _CLASSIFY_SYSTEM_PROMPT.replace("{patient_context}", context_text)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": message},
    ]

    try:
        result = await structured_call(
            response_model=ClassifyLLMResponse,
            messages=messages,
            op_name="triage.classify",
            env_var=_triage_env_var(),
            temperature=0.1,
            max_tokens=200,
            max_retries=2,
        )
    except Exception as exc:
        log(f"[triage] classify failed: {exc}", level="error")
        return TriageResult(category=TriageCategory.general_question, confidence=0.0)

    # Low confidence → safe default
    if result.confidence < 0.7:
        log(f"[triage] low confidence {result.confidence:.2f} for '{result.category.value}', escalating to general_question")
        return TriageResult(
            category=TriageCategory.general_question,
            confidence=result.confidence,
        )

    return TriageResult(
        category=result.category,
        confidence=result.confidence,
    )


# ---------------------------------------------------------------------------
# Step 2: Handlers
# ---------------------------------------------------------------------------

_INFORMATIONAL_SYSTEM_PROMPT = get_prompt_sync("intent/triage-informational")


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
    from agent.llm import structured_call

    context_text = json.dumps(context, ensure_ascii=False, indent=2)
    system = _INFORMATIONAL_SYSTEM_PROMPT.replace("{patient_context}", context_text)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": message},
    ]

    try:
        result = await structured_call(
            response_model=InformationalLLMResponse,
            messages=messages,
            op_name="triage.informational",
            env_var=_triage_env_var(),
            temperature=0.3,
            max_tokens=500,
        )
        reply = result.reply
    except Exception as exc:
        log(f"[triage] handle_informational failed: {exc}", level="error")
        reply = ""

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


_ESCALATION_SYSTEM_PROMPT = get_prompt_sync("intent/triage-escalation")


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
    from agent.llm import structured_call

    context_text = json.dumps(context, ensure_ascii=False, indent=2)
    system = _ESCALATION_SYSTEM_PROMPT.replace("{patient_context}", context_text)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": message},
    ]

    try:
        result = await structured_call(
            response_model=EscalationLLMResponse,
            messages=messages,
            op_name="triage.escalation",
            env_var=_triage_env_var(),
            temperature=0.1,
            max_tokens=800,
        )
        summary_json = result.model_dump_json()
    except Exception as exc:
        log(f"[triage] handle_escalation summary failed: {exc}", level="error")
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
