"""Pure-function unit tests for the triage module.

Tests cover:
- TriageCategory enum value stability
- TriageResult dataclass instantiation
- _is_rate_limited / _record_escalation (6-hour window)
- _should_notify / _mark_notified (10-minute quiet window)

All time-dependent functions are tested with unittest.mock.patch so that
the tests are deterministic and do not rely on wall-clock time.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

import domain.patient_lifecycle.triage_handlers as _mod
from domain.patient_lifecycle.triage import TriageCategory, TriageResult
from domain.patient_lifecycle.triage_handlers import (
    _is_rate_limited,
    _record_escalation,
    _should_notify,
    _mark_notified,
)


# ---------------------------------------------------------------------------
# Fixture: reset module-level state before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_triage_state():
    """Clear _escalation_timestamps and _last_notify_time before every test."""
    _mod._escalation_timestamps.clear()
    _mod._last_notify_time.clear()
    yield
    _mod._escalation_timestamps.clear()
    _mod._last_notify_time.clear()


# ---------------------------------------------------------------------------
# TriageCategory enum
# ---------------------------------------------------------------------------

class TestTriageCategory:
    def test_intake_value(self):
        assert TriageCategory.intake.value == "intake"

    def test_informational_value(self):
        assert TriageCategory.informational.value == "informational"

    def test_other_value(self):
        assert TriageCategory.other.value == "other"

    def test_is_str_enum(self):
        """TriageCategory inherits from str — members compare equal to their values."""
        assert TriageCategory.informational == "informational"
        assert isinstance(TriageCategory.informational, str)

    def test_all_three_members_exist(self):
        members = {c.value for c in TriageCategory}
        assert members == {"intake", "informational", "other"}


# ---------------------------------------------------------------------------
# Legacy category string parsing — read-only back-compat for old DB rows
# ---------------------------------------------------------------------------

class TestLegacyCategoryParse:
    def test_legacy_symptom_report_maps_to_intake(self):
        from domain.patient_lifecycle.triage import parse_category
        assert parse_category("symptom_report") is TriageCategory.intake

    def test_legacy_side_effect_maps_to_intake(self):
        from domain.patient_lifecycle.triage import parse_category
        assert parse_category("side_effect") is TriageCategory.intake

    def test_legacy_urgent_maps_to_intake(self):
        from domain.patient_lifecycle.triage import parse_category
        assert parse_category("urgent") is TriageCategory.intake

    def test_legacy_general_question_maps_to_other(self):
        from domain.patient_lifecycle.triage import parse_category
        assert parse_category("general_question") is TriageCategory.other

    def test_current_values_pass_through(self):
        from domain.patient_lifecycle.triage import parse_category
        assert parse_category("intake") is TriageCategory.intake
        assert parse_category("informational") is TriageCategory.informational
        assert parse_category("other") is TriageCategory.other

    def test_unknown_value_falls_back_to_other(self):
        from domain.patient_lifecycle.triage import parse_category
        assert parse_category("garbage") is TriageCategory.other
        assert parse_category("") is TriageCategory.other


# ---------------------------------------------------------------------------
# TriageResult dataclass
# ---------------------------------------------------------------------------

class TestTriageResult:
    def test_instantiation_with_category_and_confidence(self):
        result = TriageResult(
            category=TriageCategory.intake,
            confidence=0.95,
        )
        assert result.category == TriageCategory.intake
        assert result.confidence == 0.95

    def test_instantiation_with_informational(self):
        result = TriageResult(category=TriageCategory.informational, confidence=1.0)
        assert result.category == TriageCategory.informational
        assert result.confidence == 1.0

    def test_instantiation_with_other_zero_confidence(self):
        """Zero confidence is a valid sentinel for LLM failure fallback."""
        result = TriageResult(category=TriageCategory.other, confidence=0.0)
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# _is_rate_limited / _record_escalation
# ---------------------------------------------------------------------------

_PATIENT = 42
_DOCTOR = "doc-123"
_SIX_HOURS = 6 * 60 * 60


class TestIsRateLimited:
    def test_not_limited_when_no_prior_escalations(self):
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=1_000_000.0):
            assert _is_rate_limited(_PATIENT, _DOCTOR) is False

    def test_not_limited_after_one_escalation(self):
        base = 1_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _record_escalation(_PATIENT, _DOCTOR)
            assert _is_rate_limited(_PATIENT, _DOCTOR) is False

    def test_not_limited_after_two_escalations(self):
        base = 1_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _record_escalation(_PATIENT, _DOCTOR)
            _record_escalation(_PATIENT, _DOCTOR)
            assert _is_rate_limited(_PATIENT, _DOCTOR) is False

    def test_limited_after_three_escalations_within_window(self):
        base = 1_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _record_escalation(_PATIENT, _DOCTOR)
            _record_escalation(_PATIENT, _DOCTOR)
            _record_escalation(_PATIENT, _DOCTOR)
            assert _is_rate_limited(_PATIENT, _DOCTOR) is True

    def test_not_limited_after_window_expires(self):
        """Three escalations recorded at t=0; check at t > 6h — all expire."""
        base = 1_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _record_escalation(_PATIENT, _DOCTOR)
            _record_escalation(_PATIENT, _DOCTOR)
            _record_escalation(_PATIENT, _DOCTOR)

        # Advance time past the 6-hour window
        future = base + _SIX_HOURS + 1
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=future):
            assert _is_rate_limited(_PATIENT, _DOCTOR) is False

    def test_limited_only_for_matching_patient_doctor_pair(self):
        """Rate limiting is keyed per (patient_id, doctor_id) — another patient is unaffected."""
        base = 1_000_000.0
        other_patient = _PATIENT + 1

        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _record_escalation(_PATIENT, _DOCTOR)
            _record_escalation(_PATIENT, _DOCTOR)
            _record_escalation(_PATIENT, _DOCTOR)

            # The original patient is rate-limited
            assert _is_rate_limited(_PATIENT, _DOCTOR) is True
            # A different patient is not rate-limited
            assert _is_rate_limited(other_patient, _DOCTOR) is False

    def test_partially_expired_entries_are_trimmed(self):
        """Two old entries + one fresh entry → 1 valid timestamp, not limited."""
        base = 1_000_000.0
        # Record two escalations at t=0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _record_escalation(_PATIENT, _DOCTOR)
            _record_escalation(_PATIENT, _DOCTOR)

        # Advance past 6h; record one more fresh escalation
        future = base + _SIX_HOURS + 1
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=future):
            _record_escalation(_PATIENT, _DOCTOR)
            # Only 1 valid entry → not yet at the limit of 3
            assert _is_rate_limited(_PATIENT, _DOCTOR) is False


class TestRecordEscalation:
    def test_record_escalation_stores_timestamp(self):
        base = 2_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _record_escalation(_PATIENT, _DOCTOR)

        key = (_PATIENT, _DOCTOR)
        assert key in _mod._escalation_timestamps
        assert _mod._escalation_timestamps[key] == [base]

    def test_record_escalation_appends_multiple_timestamps(self):
        t1, t2 = 2_000_000.0, 2_000_001.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=t1):
            _record_escalation(_PATIENT, _DOCTOR)
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=t2):
            _record_escalation(_PATIENT, _DOCTOR)

        key = (_PATIENT, _DOCTOR)
        assert _mod._escalation_timestamps[key] == [t1, t2]


# ---------------------------------------------------------------------------
# _should_notify / _mark_notified
# ---------------------------------------------------------------------------

_TEN_MINUTES = 10 * 60


class TestShouldNotify:
    def test_should_notify_on_first_call(self):
        """No prior notification — should always notify."""
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=1_000_000.0):
            assert _should_notify(_PATIENT, _DOCTOR) is True

    def test_should_not_notify_immediately_after_mark(self):
        """Marked just now → within 10-minute window → suppress."""
        base = 1_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _mark_notified(_PATIENT, _DOCTOR)
            assert _should_notify(_PATIENT, _DOCTOR) is False

    def test_should_not_notify_just_before_window_expires(self):
        """9 minutes 59 seconds after notification → still suppressed."""
        base = 1_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _mark_notified(_PATIENT, _DOCTOR)

        just_before = base + _TEN_MINUTES - 1
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=just_before):
            assert _should_notify(_PATIENT, _DOCTOR) is False

    def test_should_notify_exactly_at_window_boundary(self):
        """Exactly 10 minutes later → window elapsed → allow notification."""
        base = 1_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _mark_notified(_PATIENT, _DOCTOR)

        at_boundary = base + _TEN_MINUTES
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=at_boundary):
            assert _should_notify(_PATIENT, _DOCTOR) is True

    def test_should_notify_after_window_expires(self):
        """More than 10 minutes later → window expired → allow notification."""
        base = 1_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _mark_notified(_PATIENT, _DOCTOR)

        future = base + _TEN_MINUTES + 60
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=future):
            assert _should_notify(_PATIENT, _DOCTOR) is True

    def test_notify_check_is_per_patient_doctor_pair(self):
        """Marking one patient does not suppress notifications for another patient."""
        base = 1_000_000.0
        other_patient = _PATIENT + 99

        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _mark_notified(_PATIENT, _DOCTOR)
            # Original patient is suppressed
            assert _should_notify(_PATIENT, _DOCTOR) is False
            # Different patient is not suppressed
            assert _should_notify(other_patient, _DOCTOR) is True


class TestMarkNotified:
    def test_mark_notified_stores_timestamp(self):
        base = 3_000_000.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=base):
            _mark_notified(_PATIENT, _DOCTOR)

        key = (_PATIENT, _DOCTOR)
        assert key in _mod._last_notify_time
        assert _mod._last_notify_time[key] == base

    def test_mark_notified_overwrites_previous_timestamp(self):
        t1, t2 = 3_000_000.0, 3_000_600.0
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=t1):
            _mark_notified(_PATIENT, _DOCTOR)
        with patch("domain.patient_lifecycle.triage_handlers.time.time", return_value=t2):
            _mark_notified(_PATIENT, _DOCTOR)

        key = (_PATIENT, _DOCTOR)
        assert _mod._last_notify_time[key] == t2
