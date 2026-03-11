"""Intent workflow — unified multi-layer intent pipeline.

Usage:
    from services.intent_workflow import run

    result = await run(text, doctor_id, history, ...)
    if not result.gate.approved:
        return ChatResponse(reply=result.gate.clarification_message)
    intent_result = result.to_intent_result()
    # dispatch to handler...
"""

from .models import (
    IntentDecision,
    EntitySlot,
    EntityResolution,
    BindingDecision,
    PlannedAction,
    ActionPlan,
    GateResult,
    WorkflowResult,
)
from .workflow import run

__all__ = [
    "run",
    "IntentDecision",
    "EntitySlot",
    "EntityResolution",
    "BindingDecision",
    "PlannedAction",
    "ActionPlan",
    "GateResult",
    "WorkflowResult",
]
