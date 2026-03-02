"""Unit tests for services/patient_categorization.py.

All tests are pure (no DB, no I/O). Patient and Record objects are built
from SimpleNamespace mocks.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import List, Optional

import pytest

from services.patient_categorization import (
    CategoryResult,
    HIGH_RISK_KEYWORDS,
    RULES_VERSION,
    categorize_patient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 2, 12, 0, 0)


def _patient(created_days_ago: float = 60) -> SimpleNamespace:
    return SimpleNamespace(created_at=_NOW - timedelta(days=created_days_ago))


def _record(
    created_days_ago: float,
    diagnosis: Optional[str] = None,
    follow_up_plan: Optional[str] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        created_at=_NOW - timedelta(days=created_days_ago),
        diagnosis=diagnosis,
        follow_up_plan=follow_up_plan,
    )


def _cat(
    patient: SimpleNamespace,
    records: List[SimpleNamespace],
) -> CategoryResult:
    return categorize_patient(patient, records, now=_NOW)


# ---------------------------------------------------------------------------
# Primary category tests
# ---------------------------------------------------------------------------

def test_high_risk_keyword_present():
    p = _patient(60)
    r = _record(5, diagnosis="急性心肌梗死 STEMI")
    result = _cat(p, [r])
    assert result.primary_category == "high_risk"
    assert result.rules_version == RULES_VERSION


def test_high_risk_wins_over_active_followup_even_with_followup_plan():
    """high_risk has higher precedence than active_followup."""
    p = _patient(60)
    r = _record(5, diagnosis="急性心衰", follow_up_plan="两周复诊")
    result = _cat(p, [r])
    assert result.primary_category == "high_risk"


@pytest.mark.parametrize("kw", HIGH_RISK_KEYWORDS)
def test_each_high_risk_keyword_triggers(kw):
    p = _patient(60)
    r = _record(5, diagnosis=f"患者诊断为{kw}型疾病")
    result = _cat(p, [r])
    assert result.primary_category == "high_risk", f"keyword={kw!r} did not trigger high_risk"


def test_active_followup_with_followup_plan_within_30_days():
    p = _patient(60)
    r = _record(15, diagnosis="高血压", follow_up_plan="下月复诊")
    result = _cat(p, [r])
    assert result.primary_category == "active_followup"


def test_active_followup_not_triggered_when_record_older_than_30_days():
    """follow_up_plan present but record is 45 days old → falls through to stable."""
    p = _patient(90)
    r = _record(45, diagnosis="高血压", follow_up_plan="下月复诊")
    result = _cat(p, [r])
    assert result.primary_category == "stable"


def test_stable_record_31_days_ago():
    p = _patient(90)
    r = _record(31, diagnosis="糖尿病")
    result = _cat(p, [r])
    assert result.primary_category == "stable"


def test_new_patient_no_records():
    p = _patient(60)
    result = _cat(p, [])
    assert result.primary_category == "new"


def test_new_patient_created_3_days_ago_no_records():
    p = _patient(3)
    result = _cat(p, [])
    assert result.primary_category == "new"


def test_new_patient_created_recently_even_with_records():
    """Patient created 3 days ago with a record → still 'new' (new patient window)."""
    p = _patient(3)
    r = _record(2, diagnosis="感冒")
    result = _cat(p, [r])
    assert result.primary_category == "new"


# ---------------------------------------------------------------------------
# Category tag tests
# ---------------------------------------------------------------------------

def test_recent_visit_tag_at_5_days():
    p = _patient(60)
    r = _record(5)
    result = _cat(p, [r])
    assert "recent_visit" in result.category_tags


def test_no_recent_visit_tag_at_100_days():
    p = _patient(120)
    r = _record(100)
    result = _cat(p, [r])
    assert "no_recent_visit" in result.category_tags


def test_needs_record_update_tag_at_45_days():
    p = _patient(90)
    r = _record(45)
    result = _cat(p, [r])
    assert "needs_record_update" in result.category_tags


def test_no_tags_for_record_at_20_days():
    """20 days: not recent_visit (>14), not no_recent_visit (<90), not needs_record_update (<30)."""
    p = _patient(60)
    r = _record(20)
    result = _cat(p, [r])
    # recent_visit threshold is 14, so 20 days = no tag
    assert "recent_visit" not in result.category_tags
    assert "no_recent_visit" not in result.category_tags
    assert "needs_record_update" not in result.category_tags


def test_recent_visit_tag_boundary_exactly_14_days():
    p = _patient(60)
    r = _record(14)
    result = _cat(p, [r])
    assert "recent_visit" in result.category_tags


def test_no_tags_for_new_patient_no_records_young():
    """Brand new patient, created 1 day ago, no records — no visit-based tags."""
    p = _patient(1)
    result = _cat(p, [])
    assert "recent_visit" not in result.category_tags
    assert "needs_record_update" not in result.category_tags


# ---------------------------------------------------------------------------
# Result metadata
# ---------------------------------------------------------------------------

def test_result_has_correct_rules_version():
    p = _patient(60)
    result = _cat(p, [])
    assert result.rules_version == RULES_VERSION


def test_result_computed_at_equals_now():
    p = _patient(60)
    result = _cat(p, [])
    assert result.computed_at == _NOW


def test_matched_rules_populated():
    p = _patient(60)
    r = _record(5, diagnosis="急性心梗")
    result = _cat(p, [r])
    assert len(result.matched_rules) > 0
    assert any("high_risk" in rule for rule in result.matched_rules)


# ---------------------------------------------------------------------------
# Precedence: multiple rules could match
# ---------------------------------------------------------------------------

def test_precedence_high_risk_beats_stable():
    p = _patient(90)
    # record is 35 days old (> 30 → stable) but has high-risk diagnosis
    r = _record(35, diagnosis="急性心衰")
    result = _cat(p, [r])
    assert result.primary_category == "high_risk"


def test_precedence_high_risk_beats_new():
    p = _patient(3)
    r = _record(2, diagnosis="恶性肿瘤")
    result = _cat(p, [r])
    assert result.primary_category == "high_risk"
