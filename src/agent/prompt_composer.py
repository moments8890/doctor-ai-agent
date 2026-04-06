"""Prompt composer — assembles the 7-layer prompt stack into messages.

Layers:
  L1 Identity      (common/base.md)         — role, safety, precedence
  L2 Specialty     (domain/{specialty}.md)   — domain knowledge
  L3 Task          (intent/{intent}.md)      — action-specific rules + format
  L4 Doctor Rules  (DB, auto-loaded)         — user-authored KB, scored
  L5 Case Memory   (DB, diagnosis only)      — similar confirmed decisions
  L6 Patient       (DB, records/history)     — caller provides
  L7 Input         (actual message)          — doctor's/patient's input

L1-L3 → single system message
L4 → auto-loaded by composer from DB when config.load_knowledge is True
L4-L7 → final user message with XML tags (Pattern 1)
       or L4-L6 in system, L7 as plain user (Pattern 2: conversation)
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from agent.prompt_config import LayerConfig, INTENT_LAYERS, ROUTING_LAYERS, REVIEW_LAYERS, PATIENT_INTERVIEW_LAYERS
from agent.types import IntentType
from utils.log import log, _ctx_layers
from utils.prompt_loader import get_prompt_sync


def _inject_date(text: str) -> str:
    """Replace {current_date} placeholder with today's date (YYYY-MM-DD)."""
    if "{current_date}" in text:
        return text.replace("{current_date}", date.today().isoformat())
    return text


async def _load_doctor_knowledge(doctor_id: str, config: LayerConfig, query: str = "", patient_context: str = "") -> str:
    """Load doctor KB items. Returns formatted text."""
    if not doctor_id or not config.load_knowledge:
        return ""
    try:
        from domain.knowledge.doctor_knowledge import load_knowledge
        result = await load_knowledge(doctor_id, query=query, patient_context=patient_context)
        log(f"[composer] KB loaded: {len(result)} chars")
        return result
    except Exception as exc:
        log(f"[composer] KB load failed (non-fatal): {exc}", level="warning")
        return ""


async def compose_messages(
    config: LayerConfig,
    *,
    doctor_id: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    specialty: str = "neurology",
    extra_system: str = "",
) -> List[Dict[str, str]]:
    """Assemble the prompt stack into a message list.

    L4 Doctor Rules is auto-loaded from DB when config.load_knowledge
    is True. Callers don't need to load KB.

    Args:
        config: LayerConfig defining which layers to include.
        doctor_id: Used for KB loading and logging.
        patient_context: Pre-formatted patient data (L6 Patient).
        doctor_message: The actual user input (L7 Input).
        history: Conversation history (between system and user).
        specialty: Doctor's specialty for L2 Specialty lookup.
        extra_system: Additional system content appended to system message.
    """
    # ── L1-L3: System message ────────────────────────────────────────
    parts = []

    # L1 Identity (always included)
    if config.system:
        base = get_prompt_sync("common/base", fallback="")
        if base:
            parts.append(base)

    # L2 Specialty
    if config.domain:
        domain = get_prompt_sync(f"domain/{specialty}", fallback="")
        if domain:
            parts.append(domain)

    # L3 Task
    intent_prompt = get_prompt_sync(f"intent/{config.intent}", fallback="")
    if intent_prompt:
        parts.append(intent_prompt)

    # Extra system content (e.g. interview context injected by handler)
    if extra_system:
        parts.append(extra_system)

    system_msg = _inject_date("\n\n".join(filter(None, parts)))

    # ── L4 Doctor Rules (auto-loaded from DB) ───────────────────────
    doctor_knowledge = await _load_doctor_knowledge(
        doctor_id, config, query=doctor_message, patient_context=patient_context,
    )

    kb_note = f" kb={len(doctor_knowledge)}chars" if doctor_knowledge else ""

    if config.conversation_mode:
        # ── Pattern 2: Conversation ───────────────────────────────
        # L1-L3 + Patient context → system message (factual DB data)
        # History → user/assistant turns
        # L4 KB + L7 Input → final user message (KB is user-authored, not system-trust)
        if config.patient_context and patient_context:
            system_msg += f"\n\n## 当前状态\n{patient_context}"

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        # KB goes in user message (trust boundary: user-authored content ≠ system instructions)
        user_parts: List[str] = []
        if doctor_knowledge:
            user_parts.append(
                f"<doctor_knowledge>\n"
                f"以下是可引用的医生知识规则。若使用其中内容，"
                f"在相关内容后追加 [KB-{{id}}] 引用标签。\n"
                f"{doctor_knowledge}\n"
                f"</doctor_knowledge>"
            )
        if doctor_message:
            user_parts.append(doctor_message)
        if user_parts:
            messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        log(f"[composer] intent={config.intent} pattern=convo system={len(system_msg)}chars{kb_note} history={len(history or [])}turns")
    else:
        # ── Pattern 1: Single-turn ────────────────────────────────
        # L1-L3 (Identity+Specialty+Task) → system message
        # L4-L7 (Doctor Rules+Patient+Input) → user message with XML tags
        user_parts = []
        if doctor_knowledge:
            user_parts.append(
                f"<doctor_knowledge>\n"
                f"以下是可引用的医生知识规则。若在 detail 中使用其中任何内容，"
                f"必须在该 detail 末尾追加对应的 [KB-{{id}}] 引用标签。\n"
                f"{doctor_knowledge}\n"
                f"</doctor_knowledge>"
            )
        if config.patient_context and patient_context:
            user_parts.append(f"<patient_context>\n{patient_context}\n</patient_context>")
        user_parts.append(f"<doctor_request>\n{doctor_message}\n</doctor_request>")
        user_msg = "\n\n".join(user_parts)

        messages = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_msg})

        log(f"[composer] intent={config.intent} pattern=single system={len(system_msg)}chars user={len(user_msg)}chars{kb_note} history={len(history or [])}turns")

    # Track active layers for LLM call logging
    active = ["L1"]
    if config.domain:
        active.append("L2")
    active.append("L3")
    if config.load_knowledge and doctor_knowledge:
        active.append("L4")
    if config.patient_context and patient_context:
        active.append("L6")
    if doctor_message:
        active.append("L7")
    _ctx_layers.set(",".join(active))

    return messages


async def compose_for_intent(
    intent: IntentType,
    *,
    doctor_id: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    specialty: str = "neurology",
    extra_system: str = "",
) -> List[Dict[str, str]]:
    """Compose messages for a routing intent."""
    config = INTENT_LAYERS[intent]
    return await compose_messages(
        config,
        doctor_id=doctor_id,
        patient_context=patient_context,
        doctor_message=doctor_message,
        history=history,
        specialty=specialty,
        extra_system=extra_system,
    )


async def compose_for_routing(
    *,
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """Compose messages for the routing LLM. Minimal layers — no knowledge or context."""
    return await compose_messages(
        ROUTING_LAYERS,
        doctor_message=doctor_message,
        history=history,
    )


async def compose_for_review(
    *,
    doctor_id: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    specialty: str = "neurology",
    extra_system: str = "",
) -> List[Dict[str, str]]:
    """Compose messages for the review/diagnosis pipeline."""
    return await compose_messages(
        REVIEW_LAYERS,
        doctor_id=doctor_id,
        patient_context=patient_context,
        doctor_message=doctor_message,
        specialty=specialty,
        extra_system=extra_system,
    )


async def compose_for_patient_interview(
    *,
    doctor_id: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    specialty: str = "neurology",
) -> List[Dict[str, str]]:
    """Compose messages for the patient interview flow."""
    return await compose_messages(
        PATIENT_INTERVIEW_LAYERS,
        doctor_id=doctor_id,
        patient_context=patient_context,
        doctor_message=doctor_message,
        history=history,
        specialty=specialty,
    )
