"""Gate layer tests: verify safety checks including unsupported-combo blocking."""

from __future__ import annotations

import pytest

from services.ai.intent import Intent
from services.intent_workflow.gate import check_gate
from services.intent_workflow.models import (
    ActionPlan,
    BindingDecision,
    EntityResolution,
    EntitySlot,
    PlannedAction,
)


def _plan(intent_value: str, **kw) -> ActionPlan:
    return ActionPlan(actions=[PlannedAction(action=intent_value)], **kw)


def _entities(name: str = "张三") -> EntityResolution:
    return EntityResolution(
        patient_name=EntitySlot(value=name, source="llm"),
    )


def _binding(status: str = "bound", source: str = "db_lookup") -> BindingDecision:
    return BindingDecision(status=status, source=source, patient_name="张三")


# ── Unsupported-combo gate ───────────────────────────────────────────────────


def test_gate_approves_read_intents():
    """Read intents (query_records) should always pass the gate."""
    plan = _plan("query_records")
    gate = check_gate(plan, Intent.query_records, _entities(), _binding(), "")
    assert gate.approved is True


def test_gate_approves_non_write_intents():
    """Non-write intents like delete_patient should pass the gate."""
    plan = _plan("delete_patient")
    gate = check_gate(plan, Intent.delete_patient, _entities(), _binding(), "")
    assert gate.approved is True


# ── Normal gate behavior preserved ──────────────────────────────────────────


def test_gate_approves_clean_read():
    plan = _plan("query_records")
    gate = check_gate(plan, Intent.query_records, _entities(), _binding(), "")
    assert gate.approved is True


def test_gate_blocks_write_without_patient():
    plan = _plan("add_record")
    binding = BindingDecision(status="no_name", source="none")
    gate = check_gate(plan, Intent.add_record, EntityResolution(), binding, "")
    assert gate.approved is False
    assert gate.reason == "no_patient_name"


def test_gate_approves_write_with_bound_patient():
    plan = _plan("add_record")
    gate = check_gate(plan, Intent.add_record, _entities(), _binding(), "张三胸痛")
    assert gate.approved is True
