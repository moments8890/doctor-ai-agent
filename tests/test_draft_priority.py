"""Tests for draft priority resolution (Codex round-5 review)."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent.style_guard import detect_defer_to_doctor
from domain.patient_lifecycle.priority import is_after_hours, resolve_draft_priority


# Defer-pattern detection
def test_detect_defer_pattern_full_form():
    assert detect_defer_to_doctor("您这情况我先转给医生，医生会尽快回复您。") is True


def test_detect_defer_pattern_short_form():
    assert detect_defer_to_doctor("您说的情况已转给医生，请先等医生回复。") is True


def test_no_defer_routine_answer():
    assert detect_defer_to_doctor("术后伤口痒是正常恢复，等14天后可以洗澡。") is False


def test_no_defer_with_just_doctor_word():
    assert detect_defer_to_doctor("如果疼痛持续，请联系您的主治医生。") is False  # mentions doctor but not defer pattern


# After-hours detection
def test_after_hours_late_evening():
    assert is_after_hours(datetime(2026, 4, 25, 22, 30)) is True
    assert is_after_hours(datetime(2026, 4, 25, 23, 59)) is True


def test_after_hours_early_morning():
    assert is_after_hours(datetime(2026, 4, 25, 3, 0)) is True
    assert is_after_hours(datetime(2026, 4, 25, 5, 59)) is True


def test_office_hours_morning():
    assert is_after_hours(datetime(2026, 4, 25, 9, 0)) is False


def test_office_hours_evening_boundary():
    assert is_after_hours(datetime(2026, 4, 25, 21, 59)) is False
    assert is_after_hours(datetime(2026, 4, 25, 22, 0)) is True   # boundary inclusive on close


def test_office_hours_morning_boundary():
    assert is_after_hours(datetime(2026, 4, 25, 6, 0)) is False
    assert is_after_hours(datetime(2026, 4, 25, 5, 59)) is True


# Priority resolution
def test_priority_normal_when_no_defer():
    assert resolve_draft_priority(deferred_to_doctor=False) is None


def test_priority_urgent_when_defer_office_hours():
    p = resolve_draft_priority(deferred_to_doctor=True, now=datetime(2026, 4, 25, 14, 0))
    assert p == "urgent"


def test_priority_critical_when_defer_after_hours():
    p = resolve_draft_priority(deferred_to_doctor=True, now=datetime(2026, 4, 25, 23, 0))
    assert p == "critical"


def test_priority_critical_when_defer_early_morning():
    p = resolve_draft_priority(deferred_to_doctor=True, now=datetime(2026, 4, 25, 4, 0))
    assert p == "critical"
