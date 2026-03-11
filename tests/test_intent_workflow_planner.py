"""Planner layer tests: verify compound action detection and single-action passthrough."""

import pytest
from services.ai.intent import Intent
from services.intent_workflow.models import (
    ActionPlan, BindingDecision, EntityResolution, EntitySlot, IntentDecision,
)
from services.intent_workflow.planner import plan_actions


def _decision(intent: Intent, **kw) -> IntentDecision:
    return IntentDecision(intent=intent, source="llm", **kw)


def _entities(extra: dict | None = None, name_slot: EntitySlot | None = None) -> EntityResolution:
    return EntityResolution(patient_name=name_slot, extra_data=extra or {})


def _binding(status: str = "not_applicable", source: str = "none", needs_review: bool = False) -> BindingDecision:
    return BindingDecision(status=status, source=source, needs_review=needs_review)


# ── Single action (no compound) ──────────────────────────────────────────────


def test_plan_add_record_known_patient():
    plan = plan_actions(
        _decision(Intent.add_record),
        _entities(),
        _binding(status="bound", source="session_id"),
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "add_record"
    assert plan.is_compound is False


def test_plan_query_records():
    plan = plan_actions(
        _decision(Intent.query_records),
        _entities(),
        _binding(),
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "query_records"
    assert plan.is_compound is False


def test_plan_create_patient_plain():
    plan = plan_actions(
        _decision(Intent.create_patient),
        _entities(),
        _binding(),
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].action == "create_patient"
    assert plan.is_compound is False


# ── Compound: create_patient + clinical content ──────────────────────────────


def test_plan_create_patient_with_clinical_content():
    plan = plan_actions(
        _decision(Intent.create_patient),
        _entities(extra={"has_clinical_content": True}),
        _binding(),
    )
    assert plan.is_compound is True
    actions = [a.action for a in plan.actions]
    assert actions == ["create_patient", "add_record"]


def test_plan_create_patient_with_structured_fields():
    plan = plan_actions(
        _decision(Intent.create_patient, structured_fields={"chief_complaint": "胸痛"}),
        _entities(),
        _binding(),
    )
    assert plan.is_compound is True
    actions = [a.action for a in plan.actions]
    assert actions == ["create_patient", "add_record"]


def test_plan_create_patient_with_reminder():
    plan = plan_actions(
        _decision(Intent.create_patient),
        _entities(extra={"has_reminder": True}),
        _binding(),
    )
    assert plan.is_compound is True
    actions = [a.action for a in plan.actions]
    assert "create_task" in actions


def test_plan_create_patient_with_clinical_and_reminder():
    plan = plan_actions(
        _decision(Intent.create_patient),
        _entities(extra={"has_clinical_content": True, "has_reminder": True}),
        _binding(),
    )
    assert plan.is_compound is True
    actions = [a.action for a in plan.actions]
    assert actions == ["create_patient", "add_record", "create_task"]


# ── Compound: add_record + unbound patient (auto-create) ─────────────────────


def test_plan_add_record_unbound_candidate_patient():
    plan = plan_actions(
        _decision(Intent.add_record),
        _entities(name_slot=EntitySlot(value="张三", source="candidate", confidence=0.6)),
        _binding(status="has_name", source="entity", needs_review=True),
    )
    assert plan.is_compound is True
    actions = [a.action for a in plan.actions]
    assert actions == ["create_patient", "add_record"]
    assert plan.actions[0].params["source"] == "auto_create"


def test_plan_add_record_unbound_not_found_patient():
    plan = plan_actions(
        _decision(Intent.add_record),
        _entities(name_slot=EntitySlot(value="李四", source="not_found", confidence=0.4)),
        _binding(status="has_name", source="entity", needs_review=True),
    )
    assert plan.is_compound is True
    actions = [a.action for a in plan.actions]
    assert actions == ["create_patient", "add_record"]


def test_plan_add_record_bound_patient_no_compound():
    """When patient is already bound (exists), no auto-create needed."""
    plan = plan_actions(
        _decision(Intent.add_record),
        _entities(name_slot=EntitySlot(value="张三", source="session", confidence=0.9)),
        _binding(status="bound", source="session_id"),
    )
    assert plan.is_compound is False
    assert len(plan.actions) == 1


# ── WorkflowResult.to_intent_result compound propagation ─────────────────────


def test_workflow_result_propagates_compound_actions():
    from services.intent_workflow.models import GateResult, WorkflowResult

    result = WorkflowResult(
        decision=_decision(Intent.create_patient),
        entities=_entities(extra={"has_clinical_content": True}),
        binding=_binding(),
        plan=plan_actions(
            _decision(Intent.create_patient),
            _entities(extra={"has_clinical_content": True}),
            _binding(),
        ),
        gate=GateResult(),
    )
    ir = result.to_intent_result()
    assert ir.extra_data.get("compound_actions") == ["create_patient", "add_record"]


def test_workflow_result_no_compound_no_key():
    from services.intent_workflow.models import GateResult, WorkflowResult

    result = WorkflowResult(
        decision=_decision(Intent.query_records),
        entities=_entities(),
        binding=_binding(),
        plan=plan_actions(_decision(Intent.query_records), _entities(), _binding()),
        gate=GateResult(),
    )
    ir = result.to_intent_result()
    assert "compound_actions" not in ir.extra_data
