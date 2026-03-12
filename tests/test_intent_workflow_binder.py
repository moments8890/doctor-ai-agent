"""Binder layer tests: patient binding from entities, session, or none."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from unittest.mock import patch

import pytest

from services.ai.intent import Intent
from services.intent_workflow.binder import bind_patient
from services.intent_workflow.models import (
    BindingDecision,
    EntityResolution,
    EntitySlot,
    IntentDecision,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _decision(intent: Intent = Intent.add_record, source: str = "llm") -> IntentDecision:
    return IntentDecision(intent=intent, source=source)


def _entities(
    name: Optional[str] = None,
    name_source: str = "llm",
) -> EntityResolution:
    if name is not None:
        return EntityResolution(
            patient_name=EntitySlot(value=name, source=name_source),
        )
    return EntityResolution()


@dataclass
class _FakeSession:
    current_patient_id: Optional[int] = None
    current_patient_name: Optional[str] = None


# ── non-patient intent → not_applicable ──────────────────────────────────────


@pytest.mark.asyncio
class TestNonPatientIntent:
    async def test_help_not_applicable(self):
        result = await bind_patient(_decision(Intent.help), _entities(), "doc1")
        assert result.status == "not_applicable"
        assert result.source == "none"

    async def test_unknown_not_applicable(self):
        result = await bind_patient(_decision(Intent.unknown), _entities(), "doc1")
        assert result.status == "not_applicable"

    async def test_list_patients_not_applicable(self):
        result = await bind_patient(_decision(Intent.list_patients), _entities(), "doc1")
        assert result.status == "not_applicable"

    async def test_list_tasks_not_applicable(self):
        result = await bind_patient(_decision(Intent.list_tasks), _entities(), "doc1")
        assert result.status == "not_applicable"


# ── name from entities ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestNameFromEntities:
    async def test_llm_source_has_name_no_review(self):
        """Entity name with source='llm' → status='has_name', needs_review=False."""
        result = await bind_patient(
            _decision(Intent.add_record),
            _entities(name="张三", name_source="llm"),
            "doc1",
        )
        assert result.status == "has_name"
        assert result.patient_name == "张三"
        assert result.source == "llm"
        assert result.needs_review is False

    async def test_fast_route_source_no_review(self):
        """Entity name with source='fast_route' → needs_review=False."""
        result = await bind_patient(
            _decision(Intent.query_records),
            _entities(name="李四", name_source="fast_route"),
            "doc1",
        )
        assert result.status == "has_name"
        assert result.needs_review is False

    async def test_candidate_source_needs_review(self):
        """Entity name with source='candidate' → needs_review=True."""
        result = await bind_patient(
            _decision(Intent.add_record),
            _entities(name="王五", name_source="candidate"),
            "doc1",
        )
        assert result.status == "has_name"
        assert result.patient_name == "王五"
        assert result.source == "candidate"
        assert result.needs_review is True

    async def test_not_found_source_needs_review(self):
        """Entity name with source='not_found' → needs_review=True."""
        result = await bind_patient(
            _decision(Intent.add_record),
            _entities(name="赵六", name_source="not_found"),
            "doc1",
        )
        assert result.status == "has_name"
        assert result.needs_review is True

    async def test_text_leading_name_no_review(self):
        """source='text_leading_name' is not candidate/not_found → no review."""
        result = await bind_patient(
            _decision(Intent.add_record),
            _entities(name="孙七", name_source="text_leading_name"),
            "doc1",
        )
        assert result.status == "has_name"
        assert result.needs_review is False


# ── session patient_id fallback ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestSessionFallback:
    @patch("services.intent_workflow.binder.get_session")
    async def test_session_patient_id_bound(self, mock_gs):
        """No entity name, session has current_patient_id → status='bound', source='session_id'."""
        mock_gs.return_value = _FakeSession(current_patient_id=42, current_patient_name="张三")
        result = await bind_patient(
            _decision(Intent.add_record),
            _entities(),  # no name
            "doc1",
        )
        assert result.status == "bound"
        assert result.source == "session_id"
        assert result.patient_id == 42
        assert result.patient_name == "张三"
        mock_gs.assert_called_once_with("doc1")

    @patch("services.intent_workflow.binder.get_session")
    async def test_session_patient_id_without_name(self, mock_gs):
        """Session has patient_id but no name → still 'bound', name is None."""
        mock_gs.return_value = _FakeSession(current_patient_id=7, current_patient_name=None)
        result = await bind_patient(
            _decision(Intent.query_records),
            _entities(),
            "doc1",
        )
        assert result.status == "bound"
        assert result.patient_id == 7
        assert result.patient_name is None


# ── no name, no session → no_name ───────────────────────────────────────────


@pytest.mark.asyncio
class TestNoName:
    @patch("services.intent_workflow.binder.get_session")
    async def test_no_name_no_session(self, mock_gs):
        """No entity name, session has no patient_id → status='no_name'."""
        mock_gs.return_value = _FakeSession()
        result = await bind_patient(
            _decision(Intent.add_record),
            _entities(),
            "doc1",
        )
        assert result.status == "no_name"
        assert result.source == "none"
        assert result.patient_id is None
        assert result.patient_name is None

    @patch("services.intent_workflow.binder.get_session")
    async def test_no_name_session_id_zero(self, mock_gs):
        """Session with patient_id=0 (falsy) → treated as no session → 'no_name'."""
        mock_gs.return_value = _FakeSession(current_patient_id=0)
        result = await bind_patient(
            _decision(Intent.add_record),
            _entities(),
            "doc1",
        )
        assert result.status == "no_name"


# ── various patient intents use binding ──────────────────────────────────────


@pytest.mark.asyncio
class TestPatientIntentsNeedBinding:
    """All _PATIENT_INTENTS should go through binding logic, not return 'not_applicable'."""

    @pytest.mark.parametrize("intent", [
        Intent.add_record,
        Intent.query_records,
        Intent.update_record,
        Intent.create_patient,
        Intent.delete_patient,
        Intent.update_patient,
        Intent.export_records,
        Intent.export_outpatient_report,
        Intent.schedule_follow_up,
        Intent.schedule_appointment,
        Intent.import_history,
    ])
    async def test_patient_intent_with_entity(self, intent: Intent):
        result = await bind_patient(
            _decision(intent),
            _entities(name="测试", name_source="llm"),
            "doc1",
        )
        assert result.status == "has_name"

    @pytest.mark.parametrize("intent", [
        Intent.help,
        Intent.unknown,
        Intent.list_patients,
        Intent.list_tasks,
        Intent.complete_task,
        Intent.postpone_task,
        Intent.cancel_task,
    ])
    async def test_non_patient_intent_always_not_applicable(self, intent: Intent):
        result = await bind_patient(
            _decision(intent),
            _entities(name="测试", name_source="llm"),
            "doc1",
        )
        assert result.status == "not_applicable"
