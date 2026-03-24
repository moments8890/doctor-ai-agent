"""Action enum — value stability and chip subset.

Updated for Plan-and-Act routing pipeline (IntentType replacing old Action enum).
Action is now a backwards-compat alias for IntentType.
"""
from agent.actions import Action, CHIP_ACTIONS
from agent.types import IntentType


def test_action_is_intent_type_alias():
    """Action is a backwards-compat alias for IntentType."""
    assert Action is IntentType


def test_action_values_are_stable():
    """Enum string values must not drift — frontend sends these over the wire."""
    assert Action.create_record.value == "create_record"
    assert Action.query_patient.value == "query_patient"
    assert Action.general.value == "general"
    assert Action.query_record.value == "query_record"
    assert Action.query_task.value == "query_task"
    assert Action.create_task.value == "create_task"


def test_action_is_str_enum():
    assert isinstance(Action.create_record, str)
    assert Action.create_record == "create_record"


def test_chip_actions_subset():
    assert CHIP_ACTIONS == {
        IntentType.create_record,
        IntentType.query_patient,
    }
    assert CHIP_ACTIONS.issubset(set(Action))
