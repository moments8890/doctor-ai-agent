"""Prompt composer — assembles the 6-layer prompt stack into messages.

Layers:
  1. Common prompt     (common/base.md)         — identity, safety, date
  2. Domain prompt     (domain/{specialty}.md)   — specialty knowledge
  3. Intent prompt     (intent/{intent}.md)      — action-specific rules
  4. Doctor knowledge  (DB, filtered by category) — auto-loaded from KB
  5. Patient context   (DB, records/history)     — caller provides
  6. User prompt       (actual message)          — doctor's input

Layers 1-3 → single system message
Layer 4 → auto-loaded by composer from DB using config.knowledge_categories
Layers 4-6 → final user message with XML tags
Conversation history sits between system and user.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from agent.prompt_config import LayerConfig, INTENT_LAYERS, ROUTING_LAYERS, REVIEW_LAYERS, PATIENT_INTERVIEW_LAYERS
from agent.types import IntentType
from utils.log import log
from utils.prompt_loader import get_prompt_sync


def _inject_date(text: str) -> str:
    """Replace {current_date} placeholder with today's date (YYYY-MM-DD)."""
    if "{current_date}" in text:
        return text.replace("{current_date}", date.today().isoformat())
    return text


async def _load_doctor_knowledge(doctor_id: str, config: LayerConfig, query: str = "") -> str:
    """Load doctor KB items filtered by config.knowledge_categories. Returns formatted text."""
    if not doctor_id or not config.knowledge_categories:
        log(f"[composer] KB skip: doctor_id={bool(doctor_id)} categories={len(config.knowledge_categories)}")
        return ""
    try:
        from domain.knowledge.doctor_knowledge import load_knowledge_by_categories
        cats = [c.value if hasattr(c, "value") else c for c in config.knowledge_categories]
        log(f"[composer] KB loading for doctor={doctor_id} categories={cats}")
        result = await load_knowledge_by_categories(
            doctor_id, config.knowledge_categories, query=query,
        )
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
    """Assemble the 6-layer prompt stack into a message list.

    Layer 4 (doctor knowledge) is auto-loaded from DB based on
    config.knowledge_categories. Callers don't need to load KB.

    Args:
        config: LayerConfig defining which layers to include.
        doctor_id: Used for KB loading and logging.
        patient_context: Pre-formatted patient data (Layer 5).
        doctor_message: The actual user input (Layer 6).
        history: Conversation history (between system and user).
        specialty: Doctor's specialty for Layer 2 lookup.
        extra_system: Additional system content appended to system message.
    """
    # ── Layers 1-3: System message ─────────────────────────────────
    parts = []

    # Layer 1: Common base (always included)
    if config.system:
        base = get_prompt_sync("common/base", fallback="")
        if base:
            parts.append(base)

    # Layer 2: Domain specialty knowledge
    if config.domain:
        domain = get_prompt_sync(f"domain/{specialty}", fallback="")
        if domain:
            parts.append(domain)

    # Layer 3: Intent-specific prompt
    intent_prompt = get_prompt_sync(f"intent/{config.intent}", fallback="")
    if intent_prompt:
        parts.append(intent_prompt)

    # Extra system content (e.g. interview context injected by handler)
    if extra_system:
        parts.append(extra_system)

    system_msg = _inject_date("\n\n".join(filter(None, parts)))

    # ── Layer 4: Doctor knowledge (auto-loaded from DB) ────────────
    doctor_knowledge = await _load_doctor_knowledge(
        doctor_id, config, query=doctor_message,
    )

    kb_note = f" kb={len(doctor_knowledge)}chars" if doctor_knowledge else ""

    if config.conversation_mode:
        # ── Pattern 2: Conversation ───────────────────────────────
        # Layers 1-5 → system message (instructions + KB + context)
        # History → user/assistant turns
        # Layer 6 → final user message (plain text, no XML)
        if doctor_knowledge:
            system_msg += f"\n\n{doctor_knowledge}"
        if config.patient_context and patient_context:
            system_msg += f"\n\n## 当前状态\n{patient_context}"

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        # Only add Layer 6 if there's a message (interview may pass empty)
        if doctor_message:
            messages.append({"role": "user", "content": doctor_message})

        log(f"[composer] intent={config.intent} pattern=convo system={len(system_msg)}chars{kb_note} history={len(history or [])}turns")
    else:
        # ── Pattern 1: Single-turn ────────────────────────────────
        # Layers 1-3 → system message
        # Layers 4-6 → user message with XML tags
        user_parts = []
        if doctor_knowledge:
            user_parts.append(f"<doctor_knowledge>\n{doctor_knowledge}\n</doctor_knowledge>")
        if config.patient_context and patient_context:
            user_parts.append(f"<patient_context>\n{patient_context}\n</patient_context>")
        user_parts.append(f"<doctor_request>\n{doctor_message}\n</doctor_request>")
        user_msg = "\n\n".join(user_parts)

        messages = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_msg})

        log(f"[composer] intent={config.intent} pattern=single system={len(system_msg)}chars user={len(user_msg)}chars{kb_note} history={len(history or [])}turns")

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
