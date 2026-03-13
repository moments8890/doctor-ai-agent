"""Intent workflow orchestrator — unified entry point for all channels.

Runs the 5-layer pipeline:
1. classify  — fast_route -> LLM dispatch
2. extract   — pull entities with provenance
3. bind      — resolve patient from session/entities
4. plan      — create action plan
5. gate      — safety check before execution
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from services.ai.intent import Intent, IntentResult
from services.session import (
    clear_candidate_patient,
    clear_patient_not_found,
    get_session,
    hydrate_session_state,
)
from utils.log import log

from .binder import bind_patient
from .classifier import classify
from .entities import extract_entities
from .gate import check_gate
from .models import HERO_WRITE_INTENTS as _HERO_WRITE_INTENTS, WorkflowResult
from .planner import plan_actions

if TYPE_CHECKING:
    from services.ai.turn_context import DoctorTurnContext

async def run(
    text: str,
    doctor_id: str,
    history: list[dict],
    *,
    original_text: Optional[str] = None,
    effective_intent: Optional[IntentResult] = None,
    knowledge_context: str = "",
    channel: str = "web",
    turn_context: Optional["DoctorTurnContext"] = None,
) -> WorkflowResult:
    """Run the full intent workflow pipeline.

    Args:
        text: Processed message text.
        doctor_id: Identifies the doctor.
        history: Recent conversation turns (already trimmed for routing).
        original_text: Raw text before processing (for safety gate).
        effective_intent: Pre-resolved intent (e.g. from menu shortcuts).
        knowledge_context: Pre-loaded doctor knowledge snippet.
        channel: "web" | "wechat" | "voice" for log prefixes.

    Returns:
        WorkflowResult with all layer outputs. Use result.to_intent_result()
        for backward-compatible handler dispatch.
    """
    original_text = original_text or text
    _t0 = time.perf_counter()

    # Consolidate knowledge: turn_context.advisory.knowledge_snippet is the
    # canonical location.  Sync with the explicit parameter so both are set.
    if turn_context is not None:
        knowledge_context = knowledge_context or turn_context.advisory.knowledge_snippet
        turn_context.advisory.knowledge_snippet = knowledge_context

    # Layer 1: Classification
    decision, raw_intent = await classify(
        text, doctor_id, history,
        effective_intent=effective_intent,
        knowledge_context=knowledge_context,
        channel=channel,
        turn_context=turn_context,
    )

    # Update provenance: mark knowledge as used if a snippet was injected
    if turn_context is not None and knowledge_context:
        turn_context.provenance.knowledge_used = True
    _t_classify = time.perf_counter()

    # Build a consistent session view for entity extraction and binding.
    # For write intents, refresh from DB first (multi-device scenarios),
    # then snapshot. For reads, use the turn_context proxy (if available)
    # or live session — same state the classifier already used.
    if decision.intent in _HERO_WRITE_INTENTS:
        await hydrate_session_state(doctor_id, write_intent=True)
    if turn_context is not None and decision.intent not in _HERO_WRITE_INTENTS:
        from .classifier import _session_proxy_from_context
        _session = _session_proxy_from_context(turn_context)
    else:
        # Post-hydration live session (write intents) or no turn_context
        _session = get_session(doctor_id)

    # Layer 2: Entity extraction
    entities = extract_entities(
        raw_intent, decision.source, text, history, doctor_id,
        session=_session,
    )
    _t_entities = time.perf_counter()

    # Consume session state for candidate/not_found to prevent re-use
    if entities.patient_name:
        if entities.patient_name.source == "candidate":
            clear_candidate_patient(doctor_id)
        elif entities.patient_name.source == "not_found":
            clear_patient_not_found(doctor_id)

    # Layer 3: Patient binding (read-only)
    binding = await bind_patient(decision, entities, doctor_id, session=_session)
    _t_bind = time.perf_counter()

    # Layer 4: Action planning
    plan = plan_actions(decision, entities, binding)

    # Layer 5: Execution gate
    gate = check_gate(plan, decision.intent, entities, binding, original_text)
    _t_done = time.perf_counter()

    result = WorkflowResult(
        decision=decision,
        entities=entities,
        binding=binding,
        plan=plan,
        gate=gate,
    )

    # Structured layer-level metrics for benchmarking
    _ms = lambda a, b: round((b - a) * 1000, 1)
    _metrics = {
        "classify_ms": _ms(_t0, _t_classify),
        "entities_ms": _ms(_t_classify, _t_entities),
        "bind_ms": _ms(_t_entities, _t_bind),
        "plan_gate_ms": _ms(_t_bind, _t_done),
        "total_ms": _ms(_t0, _t_done),
    }
    _compound_str = f" compound={[a.action for a in plan.actions]}" if plan.is_compound else ""

    log(
        f"[workflow] intent={decision.intent.value} source={decision.source} "
        f"patient={entities.patient_name.value if entities.patient_name else None}"
        f"({entities.patient_name.source if entities.patient_name else 'none'}) "
        f"binding={binding.status}/{binding.source} "
        f"gate={'OK' if gate.approved else gate.reason}{_compound_str} "
        f"latency={_metrics} "
        f"doctor={doctor_id}"
    )

    return result
