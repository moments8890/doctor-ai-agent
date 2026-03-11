"""Intent workflow orchestrator — unified entry point for all channels.

Runs the 5-layer pipeline:
1. classify  — fast_route -> LLM dispatch
2. extract   — pull entities with provenance
3. bind      — resolve patient from session/entities
4. plan      — create action plan
5. gate      — safety check before execution
"""

from __future__ import annotations

from typing import Optional

from services.ai.intent import Intent, IntentResult
from services.session import (
    clear_candidate_patient,
    clear_patient_not_found,
    hydrate_session_state,
)
from utils.log import log

from .binder import bind_patient
from .classifier import classify
from .entities import extract_entities
from .gate import check_gate
from .models import WorkflowResult
from .planner import plan_actions

_WRITE_INTENTS: frozenset[Intent] = frozenset({
    Intent.add_record,
    Intent.update_record,
})


async def run(
    text: str,
    doctor_id: str,
    history: list[dict],
    *,
    original_text: Optional[str] = None,
    followup_name: Optional[str] = None,
    effective_intent: Optional[IntentResult] = None,
    knowledge_context: str = "",
    channel: str = "web",
) -> WorkflowResult:
    """Run the full intent workflow pipeline.

    Args:
        text: Processed message text.
        doctor_id: Identifies the doctor.
        history: Recent conversation turns (already trimmed for routing).
        original_text: Raw text before processing (for safety gate).
        followup_name: If the previous turn asked for a name and the user replied.
        effective_intent: Pre-resolved intent (e.g. from menu shortcuts).
        knowledge_context: Pre-loaded doctor knowledge snippet.
        channel: "web" | "wechat" | "voice" for log prefixes.

    Returns:
        WorkflowResult with all layer outputs. Use result.to_intent_result()
        for backward-compatible handler dispatch.
    """
    original_text = original_text or text

    # Layer 1: Classification
    decision, raw_intent = await classify(
        text, doctor_id, history,
        effective_intent=effective_intent,
        knowledge_context=knowledge_context,
        channel=channel,
    )

    # For write intents, refresh session from DB before entity extraction
    # so we get fresh patient context in multi-device scenarios.
    if decision.intent in _WRITE_INTENTS:
        await hydrate_session_state(doctor_id, write_intent=True)

    # Layer 2: Entity extraction
    entities = extract_entities(
        raw_intent, decision.source, text, history, doctor_id,
        followup_name=followup_name,
    )

    # Consume session state for candidate/not_found to prevent re-use
    if entities.patient_name:
        if entities.patient_name.source == "candidate":
            clear_candidate_patient(doctor_id)
        elif entities.patient_name.source == "not_found":
            clear_patient_not_found(doctor_id)

    # Layer 3: Patient binding (read-only)
    binding = await bind_patient(decision, entities, doctor_id)

    # Layer 4: Action planning
    plan = plan_actions(decision, entities, binding)

    # Layer 5: Execution gate
    gate = check_gate(plan, decision.intent, entities, binding, original_text)

    result = WorkflowResult(
        decision=decision,
        entities=entities,
        binding=binding,
        plan=plan,
        gate=gate,
    )

    log(
        f"[workflow] intent={decision.intent.value} source={decision.source} "
        f"patient={entities.patient_name.value if entities.patient_name else None}"
        f"({entities.patient_name.source if entities.patient_name else 'none'}) "
        f"binding={binding.status}/{binding.source} "
        f"gate={'OK' if gate.approved else gate.reason} "
        f"doctor={doctor_id}"
    )

    return result
