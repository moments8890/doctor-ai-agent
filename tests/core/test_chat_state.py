"""Unit tests for ChatSessionState sticky state machine.

Tests cover:
- evaluate_entry() dual-threshold entry logic (primary + lexicon boost)
- Sticky exit from intake (classifier alone cannot exit)
- Explicit cancel signal exit
- Idle decay exit (24h for intake, 30min for qa_window)
- qa_window entry and return-to-intake transitions
"""
from __future__ import annotations

import pytest
from unittest.mock import patch
from domain.patient_lifecycle.chat_state import (
    ChatSessionState, evaluate_entry, IntakeEntryReason
)
from domain.patient_lifecycle.triage import TriageResult, TriageCategory


def _triage(category, conf):
    return TriageResult(category=category, confidence=conf)


# ---------------------------------------------------------------------------
# Entry rule tests
# ---------------------------------------------------------------------------

def test_high_confidence_symptom_enters_intake():
    decision = evaluate_entry(_triage(TriageCategory.symptom_report, 0.85), message="头晕两天了")
    assert decision.entered is True
    assert decision.reason == IntakeEntryReason.PRIMARY_THRESHOLD


def test_borderline_with_lexicon_match_enters_intake():
    decision = evaluate_entry(_triage(TriageCategory.symptom_report, 0.55), message="胃有点不舒服")
    assert decision.entered is True
    assert decision.reason == IntakeEntryReason.LEXICON_BOOST


def test_borderline_without_lexicon_match_stays_idle():
    decision = evaluate_entry(_triage(TriageCategory.symptom_report, 0.55), message="今天天气不错")
    assert decision.entered is False


def test_below_lower_threshold_never_enters():
    decision = evaluate_entry(_triage(TriageCategory.symptom_report, 0.40), message="我头很痛")
    assert decision.entered is False


def test_non_symptom_category_never_enters():
    decision = evaluate_entry(_triage(TriageCategory.general_question, 0.95), message="头痛")
    assert decision.entered is False


# ---------------------------------------------------------------------------
# Sticky exit tests
# ---------------------------------------------------------------------------

def test_intake_does_not_exit_on_low_confidence_alone():
    state = ChatSessionState(state="intake", record_id=1)
    state = state.handle_classifier_only(_triage(TriageCategory.general_question, 0.4))
    assert state.state == "intake"


def test_intake_exits_on_explicit_cancel_signal():
    state = ChatSessionState(state="intake", record_id=1)
    state = state.handle_cancel_signal(confidence=0.9)
    assert state.state == "idle"
    assert state.cancellation_reason == "patient_cancel"


def test_intake_exits_on_idle_decay():
    state = ChatSessionState(state="intake", record_id=1, last_intake_turn_at_iso="2026-04-23T08:00:00")
    state = state.apply_idle_decay(now_iso="2026-04-24T09:00:00")  # 25h elapsed
    assert state.state == "idle"
    assert state.cancellation_reason == "idle_decay"


# ---------------------------------------------------------------------------
# qa_window tests
# ---------------------------------------------------------------------------

def test_intake_enters_qa_window_on_whitelist_question():
    state = ChatSessionState(state="intake", record_id=1)
    state = state.enter_qa_window(intent="appointment_logistics")
    assert state.state == "qa_window"


def test_qa_window_returns_to_intake_on_intake_relevant_turn():
    state = ChatSessionState(state="qa_window", record_id=1)
    state = state.handle_message(_triage(TriageCategory.symptom_report, 0.7), message="还头痛")
    assert state.state == "intake"


def test_qa_window_returns_to_intake_on_30min_silence():
    state = ChatSessionState(state="qa_window", record_id=1, qa_window_entered_at_iso="2026-04-25T10:00:00")
    state = state.apply_idle_decay(now_iso="2026-04-25T10:35:00")
    assert state.state == "intake"
