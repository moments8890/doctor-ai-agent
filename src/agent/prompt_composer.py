"""Prompt composer — assembles the 6-layer prompt stack into messages.

Layers:
  1. System prompt     (system/base.md)        — identity, safety
  2. Common prompt     (common/{specialty}.md)  — specialty knowledge
  3. Intent prompt     (intent/{intent}.md)     — action-specific rules
  4. Doctor knowledge  (DB, filtered by category) — per-intent KB slice
  5. Patient context   (DB, records/history)    — lighter weight
  6. User prompt       (actual message)         — doctor's input

Layers 1-3 → single system message
Layers 4-6 → final user message with XML tags
Conversation history sits between system and user.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from agent.prompt_config import LayerConfig, INTENT_LAYERS, ROUTING_LAYERS, REVIEW_LAYERS, PATIENT_INTERVIEW_LAYERS
from agent.types import IntentType
from utils.log import log
from utils.prompt_loader import get_prompt_sync


def compose_messages(
    config: LayerConfig,
    *,
    doctor_id: str = "",
    doctor_knowledge: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    specialty: str = "neurology",
    extra_system: str = "",
) -> List[Dict[str, str]]:
    """Assemble the 6-layer prompt stack into a message list.

    Args:
        config: LayerConfig defining which layers to include.
        doctor_id: For logging/tracing.
        doctor_knowledge: Pre-formatted KB text (Layer 4).
        patient_context: Pre-formatted patient data (Layer 5).
        doctor_message: The actual user input (Layer 6).
        history: Conversation history (between system and user).
        specialty: Doctor's specialty for Layer 2 lookup.
        extra_system: Additional system content (e.g. interview-specific context
                      like collected fields, missing fields, patient info).
    """
    # ── Layers 1-3: System message ─────────────────────────────────
    parts = []

    # Layer 1: System base (always included)
    if config.system:
        base = get_prompt_sync("system/base", fallback="")
        if base:
            parts.append(base)

    # Layer 2: Common specialty knowledge
    if config.common:
        common = get_prompt_sync(f"common/{specialty}", fallback="")
        if common:
            parts.append(common)

    # Layer 3: Intent-specific prompt
    intent_prompt = get_prompt_sync(f"intent/{config.intent}", fallback="")
    if intent_prompt:
        parts.append(intent_prompt)

    # Extra system content (e.g. interview context injected by handler)
    if extra_system:
        parts.append(extra_system)

    system_msg = "\n\n".join(filter(None, parts))

    # ── Layers 4-6: User message with XML tags ─────────────────────
    user_parts = []

    # Layer 4: Doctor knowledge
    if doctor_knowledge:
        user_parts.append(f"<doctor_knowledge>\n{doctor_knowledge}\n</doctor_knowledge>")

    # Layer 5: Patient context
    if config.patient_context and patient_context:
        user_parts.append(f"<patient_context>\n{patient_context}\n</patient_context>")

    # Layer 6: User message
    user_parts.append(f"<doctor_request>\n{doctor_message}\n</doctor_request>")

    user_msg = "\n\n".join(user_parts)

    # ── Assemble: system → history → user ──────────────────────────
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_msg})

    log(f"[composer] intent={config.intent} system={len(system_msg)}chars user={len(user_msg)}chars history={len(history or [])}turns")
    return messages


def compose_for_intent(
    intent: IntentType,
    *,
    doctor_id: str = "",
    doctor_knowledge: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    specialty: str = "neurology",
    extra_system: str = "",
) -> List[Dict[str, str]]:
    """Compose messages for a routing intent."""
    config = INTENT_LAYERS[intent]
    return compose_messages(
        config,
        doctor_id=doctor_id,
        doctor_knowledge=doctor_knowledge,
        patient_context=patient_context,
        doctor_message=doctor_message,
        history=history,
        specialty=specialty,
        extra_system=extra_system,
    )


def compose_for_routing(
    *,
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    """Compose messages for the routing LLM. Minimal layers — no knowledge or context."""
    return compose_messages(
        ROUTING_LAYERS,
        doctor_message=doctor_message,
        history=history,
    )


def compose_for_review(
    *,
    doctor_id: str = "",
    doctor_knowledge: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    specialty: str = "neurology",
    extra_system: str = "",
) -> List[Dict[str, str]]:
    """Compose messages for the review/diagnosis pipeline."""
    return compose_messages(
        REVIEW_LAYERS,
        doctor_id=doctor_id,
        doctor_knowledge=doctor_knowledge,
        patient_context=patient_context,
        doctor_message=doctor_message,
        specialty=specialty,
        extra_system=extra_system,
    )


def compose_for_patient_interview(
    *,
    patient_context: str = "",
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    specialty: str = "neurology",
) -> List[Dict[str, str]]:
    """Compose messages for the patient interview flow."""
    return compose_messages(
        PATIENT_INTERVIEW_LAYERS,
        patient_context=patient_context,
        doctor_message=doctor_message,
        history=history,
        specialty=specialty,
    )
