"""Prompt composer — assembles the prompt stack into messages.

Layers:
  L1 Identity      (common/base.md)         — role, safety, precedence
  L2 Specialty     (domain/{specialty}.md)   — domain knowledge
  L3 Task          (intent/{intent}.md)      — action-specific rules + format
  L4 Doctor Rules  (DB, auto-loaded)         — user-authored KB, scored
  L6 Patient       (DB, records/history)     — caller provides
  L7 Input         (actual message)          — doctor's/patient's input

Pattern 1 (single-turn): L1-L3 system, L4+L6+L7 user with XML tags
Pattern 2 (conversation): L1-L3+Patient system, history, KB+input as user
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from agent.prompt_config import (
    LayerConfig,
    DOCTOR_INTERVIEW_LAYERS,
    REVIEW_LAYERS,
    FOLLOWUP_REPLY_LAYERS,
    PATIENT_INTERVIEW_LAYERS,
    DAILY_SUMMARY_LAYERS,
)
from agent.prompt_safety import wrap_untrusted
from utils.log import log, _ctx_layers
from utils.prompt_loader import get_prompt_sync


def _inject_date(text: str) -> str:
    """Replace {current_date} placeholder with today's date (YYYY-MM-DD)."""
    if "{current_date}" in text:
        return text.replace("{current_date}", date.today().isoformat())
    return text


async def _resolve_specialty(doctor_id: str) -> str:
    """Look up doctor's specialty from web_doctors when not passed by caller.

    Returns "" if no doctor row or no specialty set. Empty result means
    L2 is silently disabled with a log line (per round-1 codex review).
    """
    if not doctor_id:
        return ""
    try:
        from db.crud.doctor import get_doctor_by_id
        from db.engine import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            doc = await get_doctor_by_id(session, doctor_id)
            if doc and doc.specialty:
                return doc.specialty
    except Exception as exc:
        log(f"[composer] specialty lookup failed (non-fatal): {exc}", level="warning")
    return ""


async def _load_doctor_knowledge(doctor_id: str, config: LayerConfig, query: str = "", patient_context: str = "") -> tuple:
    """Load doctor KB items and active persona. Returns (knowledge_text, persona_text)."""
    knowledge = ""
    persona = ""
    if not doctor_id:
        return knowledge, persona
    if config.load_knowledge:
        try:
            from domain.knowledge.doctor_knowledge import load_knowledge
            knowledge = await load_knowledge(doctor_id, query=query, patient_context=patient_context)
            log(f"[composer] KB loaded: {len(knowledge)} chars")
        except Exception as exc:
            log(f"[composer] KB load failed (non-fatal): {exc}", level="warning")
    if config.load_persona:
        try:
            from db.crud.persona import load_active_persona_text
            from db.engine import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                persona = await load_active_persona_text(session, doctor_id)
            if persona:
                log(f"[composer] persona loaded: {len(persona)} chars")
        except Exception as exc:
            log(f"[composer] persona load failed (non-fatal): {exc}", level="warning")
    return knowledge, persona


async def compose_messages(
    config: LayerConfig,
    *,
    doctor_id: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    specialty: str = "",
    extra_system: str = "",
) -> List[Dict[str, str]]:
    """Assemble the prompt stack into a message list.

    L4 Doctor Rules is auto-loaded from DB when config.load_knowledge
    is True. Callers don't need to load KB.

    specialty: empty string means no L2 specialty layer (correct default).
    Callers should pass the doctor's actual specialty (e.g. "cardiology")
    to load domain/{specialty}.md if it exists. Missing files silently
    disable L2 and emit a log line — see "L2 disabled" in composer logs.
    """
    # ── L0-L3: System message ────────────────────────────────────────
    parts = []

    # Resolve specialty from DB if caller didn't pass one (fix for neurology
    # regression: callers historically relied on default="neurology" which
    # contaminated cardio/peds doctors. Now: lookup doctor's actual specialty.)
    if config.domain and not specialty and doctor_id:
        specialty = await _resolve_specialty(doctor_id)

    # L0 Style Guard (cross-cutting anti-AI-smell rules)
    if config.style_guard:
        guard = get_prompt_sync("common/style_guard", fallback="")
        if guard:
            parts.append(guard)

    # L1 Identity (always included)
    if config.system:
        base = get_prompt_sync("common/base", fallback="")
        if base:
            parts.append(base)

    # L2 Specialty — silent-disable + log when file missing (per round-1 codex review)
    if config.domain:
        if not specialty:
            log(f"[composer] L2 disabled: no specialty passed (intent={config.intent})")
        else:
            domain = get_prompt_sync(f"domain/{specialty}", fallback="")
            if domain:
                parts.append(domain)
            else:
                log(f"[composer] L2 disabled: no domain/{specialty}.md (intent={config.intent})")

    # L3 Task
    intent_prompt = get_prompt_sync(f"intent/{config.intent}", fallback="")
    if intent_prompt:
        parts.append(intent_prompt)

    # Extra system content (e.g. interview context injected by handler)
    if extra_system:
        parts.append(extra_system)

    system_msg = _inject_date("\n\n".join(filter(None, parts)))

    # ── L4 Doctor Rules (auto-loaded from DB) ───────────────────────
    doctor_knowledge, doctor_persona = await _load_doctor_knowledge(
        doctor_id, config, query=doctor_message, patient_context=patient_context,
    )

    kb_note = f" kb={len(doctor_knowledge)}chars" if doctor_knowledge else ""
    if doctor_persona:
        kb_note += f" persona={len(doctor_persona)}chars"

    # ── L5 Examples (corpus-clustered, runtime-routed) ──────────────
    # Per Codex round-2: deterministic top-ranked, primary cluster + at most
    # one secondary, zero examples on weak match (anchoring risk).
    examples_block = ""
    if config.load_examples and config.example_limit > 0 and doctor_message:
        try:
            from agent.example_pool import select_examples, format_examples_block
            exs = select_examples(doctor_message, k=config.example_limit)
            if exs:
                examples_block = format_examples_block(exs)
                log(f"[composer] L5 loaded {len(exs)} examples")
        except Exception as exc:
            log(f"[composer] L5 load failed (non-fatal): {exc}", level="warning")

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
        # Trust boundary: user-authored content is wrapped in tags AND its
        # angle brackets are escaped (see agent/prompt_safety.py) so a close
        # tag inside the content can't break out of the boundary.
        user_parts: List[str] = []
        if doctor_persona:
            user_parts.append(
                "<doctor_persona>\n"
                "以下是医生的个人回复风格，请按此风格起草回复。\n"
                + wrap_untrusted("persona_body", doctor_persona)
                + "\n</doctor_persona>"
            )
        if examples_block:
            user_parts.append(
                "<corpus_examples>\n"
                + wrap_untrusted("examples_body", examples_block)
                + "\n</corpus_examples>"
            )
        if doctor_knowledge:
            user_parts.append(
                "<doctor_knowledge>\n"
                "以下是可引用的医生知识规则。若使用其中内容，"
                "在相关内容后追加 [KB-{id}] 引用标签。\n"
                + wrap_untrusted("knowledge_body", doctor_knowledge)
                + "\n</doctor_knowledge>"
            )
        if doctor_message:
            user_parts.append(wrap_untrusted("doctor_message", doctor_message))
        if user_parts:
            messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        log(f"[composer] intent={config.intent} pattern=convo system={len(system_msg)}chars{kb_note} history={len(history or [])}turns")
    else:
        # ── Pattern 1: Single-turn ────────────────────────────────
        # L1-L3 (Identity+Specialty+Task) → system message
        # L4-L7 (Doctor Rules+Patient+Input) → user message with XML tags
        # Trust boundary: every user-authored field is wrapped via
        # wrap_untrusted() so embedded close tags become &lt;/foo&gt; text
        # rather than parseable structure.
        user_parts = []
        if doctor_persona:
            user_parts.append(
                "<doctor_persona>\n"
                "以下是医生的个人回复风格，请按此风格起草回复。\n"
                + wrap_untrusted("persona_body", doctor_persona)
                + "\n</doctor_persona>"
            )
        if examples_block:
            user_parts.append(
                "<corpus_examples>\n"
                + wrap_untrusted("examples_body", examples_block)
                + "\n</corpus_examples>"
            )
        if doctor_knowledge:
            user_parts.append(
                "<doctor_knowledge>\n"
                "以下是可引用的医生知识规则。若在 detail 中使用其中任何内容，"
                "必须在该 detail 末尾追加对应的 [KB-{id}] 引用标签。\n"
                + wrap_untrusted("knowledge_body", doctor_knowledge)
                + "\n</doctor_knowledge>"
            )
        if config.patient_context and patient_context:
            user_parts.append(wrap_untrusted("patient_context", patient_context))
        user_parts.append(wrap_untrusted("doctor_request", doctor_message))
        user_msg = "\n\n".join(user_parts)

        messages = [{"role": "system", "content": system_msg}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_msg})

        log(f"[composer] intent={config.intent} pattern=single system={len(system_msg)}chars user={len(user_msg)}chars{kb_note} history={len(history or [])}turns")

    # Track active layers for LLM call logging
    active = []
    if config.style_guard:
        active.append("L0")
    active.append("L1")
    if config.domain:
        active.append("L2")
    active.append("L3")
    if config.load_knowledge and doctor_knowledge:
        active.append("L4")
    if doctor_persona:
        active.append("L4p")
    if examples_block:
        active.append("L5")
    if config.patient_context and patient_context:
        active.append("L6")
    if doctor_message:
        active.append("L7")
    _ctx_layers.set(",".join(active))

    return messages


async def compose_for_doctor_interview(
    *,
    doctor_id: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    history: Optional[List[Dict[str, str]]] = None,
    specialty: str = "",
    extra_system: str = "",
    template_id: str = "medical_general_v1",  # Accepted for Phase 1 plumbing; currently ignored.
) -> List[Dict[str, str]]:
    """Compose messages for the doctor interview flow."""
    return await compose_messages(
        DOCTOR_INTERVIEW_LAYERS,
        doctor_id=doctor_id,
        patient_context=patient_context,
        doctor_message=doctor_message,
        history=history,
        specialty=specialty,
        extra_system=extra_system,
    )


async def compose_for_review(
    *,
    doctor_id: str = "",
    patient_context: str = "",
    doctor_message: str = "",
    specialty: str = "",
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
    specialty: str = "",
    template_id: str = "medical_general_v1",  # Accepted for Phase 1 plumbing; currently ignored.
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


async def compose_for_daily_summary(
    *,
    doctor_id: str = "",
    doctor_message: str = "",
    specialty: str = "",
) -> List[Dict[str, str]]:
    """Compose messages for the daily summary generation.

    doctor_message contains the serialized fact pack JSON.
    KB is auto-loaded via DAILY_SUMMARY_LAYERS.load_knowledge=True.
    """
    return await compose_messages(
        DAILY_SUMMARY_LAYERS,
        doctor_id=doctor_id,
        doctor_message=doctor_message,
        specialty=specialty,
    )
