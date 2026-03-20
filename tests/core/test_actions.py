"""Action enum — value stability and chip subset."""
from agent.actions import Action, CHIP_ACTIONS


def test_action_values_are_stable():
    """Enum string values must not drift — frontend sends these over the wire."""
    assert Action.daily_summary.value == "daily_summary"
    assert Action.create_record.value == "create_record"
    assert Action.query_patient.value == "query_patient"
    assert Action.diagnosis.value == "diagnosis"
    assert Action.general.value == "general"


def test_action_is_str_enum():
    assert isinstance(Action.daily_summary, str)
    assert Action.daily_summary == "daily_summary"


def test_chip_actions_subset():
    assert CHIP_ACTIONS == {
        Action.daily_summary,
        Action.create_record,
        Action.query_patient,
        Action.diagnosis,
    }
    assert CHIP_ACTIONS.issubset(set(Action))
