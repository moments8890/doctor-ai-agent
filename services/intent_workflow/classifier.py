"""Layer 1: Intent classification — wraps fast_route + LLM dispatch."""

from __future__ import annotations

import time
from typing import Optional

from services.ai.fast_router import fast_route, fast_route_label
from services.ai.intent import IntentResult
from services.observability.turn_log import log_turn
from services.session import get_session
from utils.log import log

from .models import IntentDecision


def _decision_from(result: IntentResult, source: str) -> IntentDecision:
    """Convert IntentResult -> IntentDecision (classification metadata only)."""
    return IntentDecision(
        intent=result.intent,
        confidence=result.confidence,
        source=source,
        chat_reply=result.chat_reply,
        structured_fields=result.structured_fields,
    )


async def classify(
    text: str,
    doctor_id: str,
    history: list[dict],
    *,
    effective_intent: Optional[IntentResult] = None,
    knowledge_context: str = "",
    channel: str = "web",
) -> tuple[IntentDecision, IntentResult]:
    """Classify intent via fast_route -> LLM dispatch.

    Returns (IntentDecision, raw IntentResult). The raw result carries entity
    data (patient_name, gender, age) consumed by the entity extraction layer.
    """
    if effective_intent is not None:
        log(f"[{channel}] menu_shortcut intent={effective_intent.intent.value} doctor={doctor_id}")
        return _decision_from(effective_intent, "menu_shortcut"), effective_intent

    session = get_session(doctor_id)
    _t0 = time.perf_counter()

    # Stage 1: fast_route (regex/rules, ~0-5 ms, no LLM)
    _fast = fast_route(text, session=session)
    if _fast is not None:
        _ms = (time.perf_counter() - _t0) * 1000.0
        log(f"[{channel}] fast_route hit: {fast_route_label(text)} doctor={doctor_id}")
        log_turn(text, _fast.intent.value, "fast", doctor_id, _ms, patient_name=_fast.patient_name)
        return _decision_from(_fast, "fast_route"), _fast

    # Stage 2: LLM dispatch (~1-3 s)
    from services.ai.agent import dispatch as agent_dispatch

    kwargs = _build_llm_kwargs(doctor_id, history, knowledge_context, session)
    intent_result = await agent_dispatch(text, **kwargs)
    _ms = (time.perf_counter() - _t0) * 1000.0
    log_turn(text, intent_result.intent.value, "llm", doctor_id, _ms, patient_name=intent_result.patient_name)
    return _decision_from(intent_result, "llm"), intent_result


def _build_llm_kwargs(
    doctor_id: str,
    history: list[dict],
    knowledge_context: str,
    session: object,
) -> dict:
    """Build keyword arguments for agent_dispatch from session context."""
    kwargs: dict = {"history": history, "doctor_id": doctor_id}
    if knowledge_context:
        kwargs["knowledge_context"] = knowledge_context
    if getattr(session, "specialty", None):
        kwargs["specialty"] = session.specialty  # type: ignore[union-attr]
    if getattr(session, "doctor_name", None):
        kwargs["doctor_name"] = session.doctor_name  # type: ignore[union-attr]
    if getattr(session, "current_patient_name", None):
        kwargs["current_patient_context"] = session.current_patient_name  # type: ignore[union-attr]
    _cand = getattr(session, "candidate_patient_name", None)
    if _cand:
        parts = [_cand]
        _cg = getattr(session, "candidate_patient_gender", None)
        _ca = getattr(session, "candidate_patient_age", None)
        if _cg:
            parts.append(_cg)
        if _ca:
            parts.append(f"{_ca}岁")
        kwargs["candidate_patient_context"] = "，".join(parts)
    if getattr(session, "patient_not_found_name", None):
        kwargs["patient_not_found_context"] = session.patient_not_found_name  # type: ignore[union-attr]
    return kwargs
