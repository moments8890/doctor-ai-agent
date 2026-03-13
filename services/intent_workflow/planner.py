"""Layer 4: Action planning — translate intent + entities + binding into an action plan.

Detects compound actions:
- create_patient + clinical content → [create_patient, add_record]
- create_patient + reminder → [..., create_task]
- add_record + reminder → [add_record, create_task]
"""

from __future__ import annotations

from services.ai.intent import Intent

from .models import ActionPlan, BindingDecision, EntityResolution, IntentDecision, PlannedAction


def plan_actions(
    decision: IntentDecision,
    entities: EntityResolution,
    binding: BindingDecision,
) -> ActionPlan:
    """Generate an action plan from the classified intent and resolved context.

    Detects compound patterns and flags them so handlers can coordinate
    rather than duplicating detection logic.
    """
    intent = decision.intent
    extra = entities.extra_data

    primary = PlannedAction(action=intent.value)
    actions = [primary]
    is_compound = False

    # Compound: create_patient with clinical content and/or reminder
    if intent == Intent.create_patient:
        if extra.get("has_clinical_content") or decision.structured_fields:
            actions.append(PlannedAction(
                action=Intent.add_record.value,
                params={"source": "compound_create"},
            ))
            is_compound = True
        if extra.get("has_reminder"):
            actions.append(PlannedAction(
                action="create_task",
                params={"source": "compound_create"},
            ))
            is_compound = True

    if intent == Intent.add_record and extra.get("has_reminder"):
        actions.append(PlannedAction(
            action="create_task",
            params={"source": "compound_record"},
        ))
        is_compound = True

    return ActionPlan(actions=actions, is_compound=is_compound)
