"""Layer 4: Action planning — translate intent + entities + binding into an action plan.

Phase 2: one action per intent. Phase 4 will add compound action support
(e.g. create_patient + add_record in a single turn).
"""

from __future__ import annotations

from .models import ActionPlan, BindingDecision, EntityResolution, IntentDecision, PlannedAction


def plan_actions(
    decision: IntentDecision,
    entities: EntityResolution,
    binding: BindingDecision,
) -> ActionPlan:
    """Generate an action plan from the classified intent and resolved context."""
    actions = [PlannedAction(action=decision.intent.value)]
    return ActionPlan(actions=actions, is_compound=False)
