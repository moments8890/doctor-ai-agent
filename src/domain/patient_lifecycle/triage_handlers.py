"""Triage handlers for patient messages (ADR 0020).

Contains the per-category handler functions (informational, escalation)
along with their shared helpers: rate limiting, notification batching, patient
name lookup, and LLM response models.

Under the 3-category triage model, ``urgent`` is no longer a separate path —
symptom-shaped messages all flow through intake; non-intake messages get a
doctor draft via ``handle_escalation``. Doctor-side urgency comes from
``MessageDraft.priority`` and ``ai_suggestions.urgency``.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.patient_message import save_patient_message
from db.models.patient import Patient
from domain.tasks.notifications import send_doctor_notification
from utils.log import log, safe_create_task
from utils.prompt_loader import get_prompt_sync


# ---------------------------------------------------------------------------
# LLM response models
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# LLM provider helper
# ---------------------------------------------------------------------------

def _triage_env_var() -> str:
    """Resolve env var for triage LLM: TRIAGE_LLM → ROUTING_LLM → groq."""
    if os.environ.get("TRIAGE_LLM"):
        return "TRIAGE_LLM"
    return "ROUTING_LLM"


# ---------------------------------------------------------------------------
# Rate limiting — max 3 escalations per 6-hour window per patient
# ---------------------------------------------------------------------------

_RATE_LIMIT_WINDOW = 6 * 60 * 60  # 6 hours in seconds
_RATE_LIMIT_MAX = 3

# Key: (patient_id, doctor_id) → list of timestamps (epoch seconds)
_escalation_timestamps: Dict[tuple, List[float]] = {}


def _is_rate_limited(patient_id: int, doctor_id: str) -> bool:
    """Return True if the patient has exceeded the escalation notification limit.

    Trims expired entries on each call.
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
    """Return True if enough time has passed since the last notification."""
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
# Background draft reply generation (30-second batching)
# ---------------------------------------------------------------------------

# Key: patient_id → dict with task handle and metadata
_pending_drafts: Dict[int, Dict[str, Any]] = {}

_DRAFT_BATCH_DELAY = 5  # seconds — short delay for low-volume pilot


async def _generate_draft_for_escalated(
    doctor_id: str,
    patient_id: int,
    message_id: int,
    message_text: str,
    patient_context: str = "",
    force_priority: Optional[str] = None,
) -> None:
    """Generate a draft reply after a delay (batches rapid-fire messages).

    If a newer message arrives for the same patient within the delay window,
    the previous pending draft is cancelled and replaced. When the timer fires,
    collects ALL unresponded inbound messages for a comprehensive reply.

    ``force_priority`` flows through to the draft persistence so signal-flag
    callers can pin priority="critical" without depending on the LLM emitting
    a defer-to-doctor phrase.
    """
    # Cancel any pending draft for this patient (newer message supersedes)
    if patient_id in _pending_drafts:
        old_task = _pending_drafts[patient_id].get("task")
        if old_task and not old_task.done():
            old_task.cancel()

    async def _delayed_generate() -> None:
        await asyncio.sleep(_DRAFT_BATCH_DELAY)
        try:
            from domain.patient_lifecycle.draft_reply import generate_draft_reply

            await generate_draft_reply(
                doctor_id, patient_id, message_id, message_text, patient_context,
                force_priority=force_priority,
            )
            log(f"[escalation] draft generated for message {message_id}")
        except Exception as e:
            log(f"[escalation] draft generation failed: {e}", level="warning")
        finally:
            _pending_drafts.pop(patient_id, None)

    task = asyncio.create_task(_delayed_generate(), name=f"draft-reply-{message_id}")
    _pending_drafts[patient_id] = {"task": task, "doctor_id": doctor_id}


# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

_INFORMATIONAL_SYSTEM_PROMPT = get_prompt_sync("intent/triage-informational")
_ESCALATION_SYSTEM_PROMPT = get_prompt_sync("intent/triage-escalation")


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def _build_context_summary(context: dict) -> str:
    """Extract a short doctor-facing summary from L6 Patient context."""
    stable_history = context.get("stable_history") or {}
    latest_record = context.get("latest_record") or {}

    parts: List[str] = []
    diagnosis = latest_record.get("diagnosis")
    if diagnosis:
        parts.append("最近诊断：{0}".format(diagnosis))

    past_history = stable_history.get("past_history") or latest_record.get("past_history")
    if past_history:
        parts.append("既往史：{0}".format(past_history))

    allergy_history = stable_history.get("allergy_history") or latest_record.get("allergy_history")
    if allergy_history:
        parts.append("过敏史：{0}".format(allergy_history))

    followup = latest_record.get("orders_followup")
    if followup:
        parts.append("随访计划：{0}".format(followup))

    return "；".join(parts[:4])


def _context_needles(context: dict) -> List[str]:
    stable_history = context.get("stable_history") or {}
    latest_record = context.get("latest_record") or {}
    candidates = [
        latest_record.get("diagnosis"),
        stable_history.get("past_history") or latest_record.get("past_history"),
        stable_history.get("allergy_history") or latest_record.get("allergy_history"),
        latest_record.get("orders_followup"),
    ]
    return [item for item in candidates if item]


def _merge_context_into_summary(summary: Dict[str, str], context: dict) -> Dict[str, str]:
    """Ensure the doctor-facing summary carries forward relevant L6 Patient history."""
    context_summary = _build_context_summary(context)
    if not context_summary:
        return summary

    summary_text = json.dumps(summary, ensure_ascii=False)
    if any(needle in summary_text for needle in _context_needles(context)):
        return summary

    merged = dict(summary)
    existing = (merged.get("conversation_context") or "").strip()
    merged["conversation_context"] = (
        "{0}；{1}".format(context_summary, existing) if existing else context_summary
    )
    return merged


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_informational(
    message: str,
    context: dict,
    db_session: AsyncSession,
    patient_id: int,
    doctor_id: str,
) -> str:
    """Handle an informational message: save inbound, generate draft for doctor.

    No auto-reply to patient. All replies go through doctor review via draft_reply.
    """
    # Persist inbound patient message
    saved_msg = await save_patient_message(
        db_session,
        patient_id=patient_id,
        doctor_id=doctor_id,
        content=message,
        direction="inbound",
        source="patient",
        ai_handled=False,
        triage_category="informational",
    )

    # Generate draft reply for doctor review
    try:
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        safe_create_task(
            _generate_draft_for_escalated(
                doctor_id, patient_id, saved_msg.id, message, context_str,
            ),
            name=f"draft-reply-{saved_msg.id}",
        )
    except Exception as exc:
        log(f"[triage] failed to schedule draft generation: {exc}", level="warning")

    return ""


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
        summary_payload = _merge_context_into_summary(result.model_dump(), context)
        summary_json = json.dumps(summary_payload, ensure_ascii=False)
    except Exception as exc:
        log(f"[triage] handle_escalation summary failed: {exc}", level="error")
        # Still escalate even if summary generation fails
        summary_json = json.dumps(_merge_context_into_summary({
            "patient_question": message,
            "conversation_context": "",
            "patient_status": "未知",
            "reason_for_escalation": f"分类为{category}，摘要生成失败",
            "suggested_action": "请查看患者消息",
        }, context), ensure_ascii=False)

    # Persist inbound patient message with escalation metadata
    saved_msg = await save_patient_message(
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

    # Fire-and-forget: generate AI draft reply for the doctor
    try:
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        safe_create_task(
            _generate_draft_for_escalated(
                doctor_id, patient_id, saved_msg.id, message, context_str,
            ),
            name=f"draft-reply-{saved_msg.id}",
        )
    except Exception as exc:
        log(f"[triage] failed to schedule draft generation: {exc}", level="warning")

    # Notify doctor (rate-limited, batched)
    if not _is_rate_limited(patient_id, doctor_id):
        _record_escalation(patient_id, doctor_id)
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
    else:
        log(f"[triage] rate-limited escalation for patient {patient_id}, skipping notification")

    # No auto-reply to patient — all replies go through doctor review
    return ""


