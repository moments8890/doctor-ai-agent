"""Tests for pure helper functions in domain.records.pdf_helpers."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from domain.records.pdf_helpers import (
    _allowed_fields,
    _age_from_year,
    _fmt_datetime,
    _record_type_label,
)


# ---------------------------------------------------------------------------
# _allowed_fields
# ---------------------------------------------------------------------------


def test_allowed_fields_none_returns_none():
    """Passing None means 'all fields' — should propagate None unchanged."""
    assert _allowed_fields(None) is None


def test_allowed_fields_empty_set_returns_empty():
    assert _allowed_fields(set()) == set()


def test_allowed_fields_diagnosis_section():
    result = _allowed_fields({"diagnosis"})
    assert result == {"diagnosis", "final_diagnosis", "key_symptoms"}


def test_allowed_fields_visits_section():
    result = _allowed_fields({"visits"})
    assert result == {
        "chief_complaint",
        "present_illness",
        "past_history",
        "physical_exam",
        "specialist_exam",
        "auxiliary_exam",
        "treatment_plan",
        "orders_followup",
    }


def test_allowed_fields_prescriptions_section():
    result = _allowed_fields({"prescriptions"})
    assert result == {"orders_followup"}


def test_allowed_fields_allergies_section():
    result = _allowed_fields({"allergies"})
    assert result == {"allergy_history"}


def test_allowed_fields_multiple_sections_union():
    result = _allowed_fields({"diagnosis", "allergies"})
    assert result == {"diagnosis", "final_diagnosis", "key_symptoms", "allergy_history"}


def test_allowed_fields_overlapping_sections_no_duplicates():
    """visits and prescriptions both include orders_followup; union deduplicates."""
    result = _allowed_fields({"visits", "prescriptions"})
    assert isinstance(result, set)
    assert "orders_followup" in result


def test_allowed_fields_unknown_section_ignored():
    """An unrecognised section name contributes no fields."""
    result = _allowed_fields({"nonexistent_section"})
    assert result == set()


def test_allowed_fields_basic_section_not_in_map_returns_empty():
    """'basic' is listed in VALID_SECTIONS but has no entry in _SECTION_FIELDS."""
    result = _allowed_fields({"basic"})
    assert result == set()


# ---------------------------------------------------------------------------
# _record_type_label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "record_type, expected",
    [
        ("visit", "门诊"),
        ("dictation", "口述"),
        ("import", "导入"),
        ("interview_summary", "问诊总结"),
    ],
)
def test_record_type_label_known_types(record_type, expected):
    assert _record_type_label(record_type) == expected


def test_record_type_label_unknown_returns_value():
    """Unknown types pass through unchanged."""
    assert _record_type_label("custom_type") == "custom_type"


def test_record_type_label_none_defaults_to_visit_label():
    """None input should default to 门诊 (same as 'visit')."""
    assert _record_type_label(None) == "门诊"


def test_record_type_label_empty_string_defaults_to_visit_label():
    assert _record_type_label("") == "门诊"


# ---------------------------------------------------------------------------
# _fmt_datetime
# ---------------------------------------------------------------------------


def test_fmt_datetime_none_returns_dash():
    assert _fmt_datetime(None) == "—"


def test_fmt_datetime_naive_datetime_formats_correctly():
    dt = datetime(2024, 6, 15, 9, 5)
    assert _fmt_datetime(dt) == "2024-06-15 09:05"


def test_fmt_datetime_midnight():
    dt = datetime(2024, 1, 1, 0, 0)
    assert _fmt_datetime(dt) == "2024-01-01 00:00"


def test_fmt_datetime_end_of_day():
    dt = datetime(2023, 12, 31, 23, 59)
    assert _fmt_datetime(dt) == "2023-12-31 23:59"


def test_fmt_datetime_seconds_not_included():
    """Seconds should be stripped — format is YYYY-MM-DD HH:MM only."""
    dt = datetime(2024, 3, 7, 14, 30, 45)
    result = _fmt_datetime(dt)
    assert result == "2024-03-07 14:30"
    assert "45" not in result


def test_fmt_datetime_with_timezone():
    """A tz-aware datetime should still format correctly."""
    from datetime import timezone
    dt = datetime(2024, 6, 15, 9, 5, tzinfo=timezone.utc)
    assert _fmt_datetime(dt) == "2024-06-15 09:05"


# ---------------------------------------------------------------------------
# _age_from_year
# ---------------------------------------------------------------------------


def test_age_from_year_none_returns_none():
    assert _age_from_year(None) is None


def test_age_from_year_zero_returns_none():
    """0 is falsy and should be treated as missing."""
    assert _age_from_year(0) is None


def test_age_from_year_calculation():
    with patch("domain.records.pdf_helpers.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 1, 1)
        result = _age_from_year(1990)
    assert result == 35


def test_age_from_year_born_this_year():
    with patch("domain.records.pdf_helpers.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 6, 1)
        result = _age_from_year(2025)
    assert result == 0


def test_age_from_year_string_coerced_to_int():
    """Year may arrive as a string; function casts via int()."""
    with patch("domain.records.pdf_helpers.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2025, 1, 1)
        result = _age_from_year("1985")
    assert result == 40


def test_age_from_year_deterministic_across_calls():
    """Two calls with the same mocked year should return the same age."""
    with patch("domain.records.pdf_helpers.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 3, 28)
        age1 = _age_from_year(2000)
        age2 = _age_from_year(2000)
    assert age1 == age2 == 26
