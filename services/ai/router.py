"""统一路由入口：fast_route → agent dispatch，供 records.py 和 wechat.py 调用。"""

from __future__ import annotations

import time

from services.ai.agent import dispatch as agent_dispatch
from services.ai.fast_router import fast_route, fast_route_label
from services.ai.intent import IntentResult
from services.observability.turn_log import log_turn
from services.session import get_session
from utils.log import log


def _build_dispatch_kwargs(
    history: list[dict],
    doctor_id: str,
    knowledge_context: str,
    session: object,
) -> dict:
    """Assemble keyword arguments for agent_dispatch from session context."""
    kwargs: dict = {"history": history, "doctor_id": doctor_id}
    if knowledge_context:
        kwargs["knowledge_context"] = knowledge_context
    if session.specialty:  # type: ignore[union-attr]
        kwargs["specialty"] = session.specialty  # type: ignore[union-attr]
    if session.doctor_name:  # type: ignore[union-attr]
        kwargs["doctor_name"] = session.doctor_name  # type: ignore[union-attr]
    # Inject current patient as explicit context so the LLM knows who is active
    # even when conversation history has been trimmed.
    if session.current_patient_name:  # type: ignore[union-attr]
        kwargs["current_patient_context"] = session.current_patient_name  # type: ignore[union-attr]
    return kwargs


async def route_message(
    text: str,
    doctor_id: str,
    history: list[dict],
    *,
    knowledge_context: str = "",
    channel: str = "unknown",
) -> IntentResult:
    """Resolve intent for *text* using fast_route then agent dispatch.

    Args:
        text: Cleaned message text (caller is responsible for stripping).
        doctor_id: Identifies the doctor; used for session lookup and logging.
        history: Recent conversation turns in [{"role": ..., "content": ...}] format.
        knowledge_context: Pre-loaded doctor knowledge base snippet (optional).
        channel: "web" | "wechat" | "voice" — used only for log prefixes.
    """
    session = get_session(doctor_id)
    _t0 = time.perf_counter()

    # Stage 1: fast_route (regex/rules, ~0–5 ms, no LLM)
    _fast = fast_route(text, session=session)
    if _fast is not None:
        _latency_ms = (time.perf_counter() - _t0) * 1000.0
        log(f"[{channel}] fast_route hit: {fast_route_label(text)} doctor={doctor_id}")
        log_turn(text, _fast.intent.value, "fast", doctor_id, _latency_ms, patient_name=_fast.patient_name)
        return _fast

    # Stage 2: agent dispatch (LLM, ~1–3 s)
    dispatch_kwargs = _build_dispatch_kwargs(history, doctor_id, knowledge_context, session)
    intent_result = await agent_dispatch(text, **dispatch_kwargs)
    _latency_ms = (time.perf_counter() - _t0) * 1000.0
    log_turn(text, intent_result.intent.value, "llm", doctor_id, _latency_ms, patient_name=intent_result.patient_name)
    return intent_result
