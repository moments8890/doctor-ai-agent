"""Protocol surface smoke tests — shapes only, not behavior."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.intake.protocols import (
    FieldSpec, Mode, Phase,
    CompletenessState, PersistRef, TurnResult, SessionState,
)


def test_fieldspec_minimal_string_field():
    spec = FieldSpec(name="chief_complaint", description="Patient's main complaint.")
    assert spec.name == "chief_complaint"
    assert spec.type == "string"
    assert spec.tier == "optional"
    assert spec.appendable is False
    assert spec.carry_forward_modes == frozenset()


def test_fieldspec_enum_requires_values():
    with pytest.raises(ValidationError):
        FieldSpec(name="severity", type="enum", description="", enum_values=None)


def test_fieldspec_carry_forward_is_frozenset():
    spec = FieldSpec(
        name="past_history", description="",
        carry_forward_modes=frozenset({"doctor"}),
    )
    assert "doctor" in spec.carry_forward_modes
    # Immutable by construction
    with pytest.raises(AttributeError):
        spec.carry_forward_modes.add("patient")


def test_fieldspec_tier_vocabulary_is_frozen():
    with pytest.raises(ValidationError):
        FieldSpec(name="x", description="", tier="urgent")  # not in Literal


def test_fieldspec_type_vocabulary_is_frozen():
    with pytest.raises(ValidationError):
        FieldSpec(name="x", description="", type="datetime")  # not in Literal


def test_mode_literal():
    # Mode should be an alias usable in annotations
    from typing import get_args
    assert set(get_args(Mode)) == {"patient", "doctor"}


def test_completenessstate_shape():
    state = CompletenessState(
        can_complete=True,
        required_missing=[],
        recommended_missing=["past_history"],
        optional_missing=[],
        next_focus="past_history",
    )
    assert state.can_complete is True
    assert state.next_focus == "past_history"


def test_turnresult_shape():
    state = CompletenessState(
        can_complete=False, required_missing=["chief_complaint"],
        recommended_missing=[], optional_missing=[], next_focus="chief_complaint",
    )
    result = TurnResult(reply="ok", suggestions=[], state=state)
    assert result.reply == "ok"


def test_persistref_shape():
    ref = PersistRef(kind="medical_record", id=42)
    assert ref.kind == "medical_record"
    assert ref.id == 42
