from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from services.patient.patient_risk import _compute_cvd_risk, compute_patient_risk


def _patient(**kwargs):
    data = {
        "created_at": datetime(2026, 1, 1, 0, 0, 0),
        "primary_category": "new",
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def _record(**kwargs):
    # Support old-style diagnosis/follow_up_plan kwargs by mapping to content
    diagnosis = kwargs.pop("diagnosis", "高血压")
    follow_up_plan = kwargs.pop("follow_up_plan", None)
    parts = [p for p in [diagnosis, follow_up_plan] if p]
    data = {
        "created_at": datetime(2026, 3, 1, 10, 0, 0),
        "content": " ".join(parts) if parts else None,
        "tags": None,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_compute_patient_risk_low_for_new_patient_without_records():
    now = datetime(2026, 3, 2, 12, 0, 0)
    result = compute_patient_risk(_patient(), records=[], now=now)

    assert result.primary_risk_level == "low"
    assert result.follow_up_state == "not_needed"
    assert "no_records" in result.risk_tags


def test_compute_patient_risk_high_with_keyword():
    now = datetime(2026, 3, 2, 12, 0, 0)
    record = _record(diagnosis="急性心梗", follow_up_plan="两周复诊")
    result = compute_patient_risk(_patient(), records=[record], now=now)

    assert result.primary_risk_level == "high"
    assert result.follow_up_state == "scheduled"
    assert "high_risk_keyword" in result.risk_tags


def test_compute_patient_risk_critical_with_critical_keyword():
    now = datetime(2026, 3, 2, 12, 0, 0)
    record = _record(diagnosis="急诊PCI后观察")
    result = compute_patient_risk(_patient(), records=[record], now=now)

    assert result.primary_risk_level == "critical"
    assert result.risk_score >= 90


def test_compute_patient_risk_upgrades_when_follow_up_overdue():
    now = datetime(2026, 3, 2, 12, 0, 0)
    old_record = _record(
        created_at=now - timedelta(days=21),
        diagnosis="高血压",
        follow_up_plan="两周复诊",
    )
    result = compute_patient_risk(_patient(), records=[old_record], now=now)

    assert result.follow_up_state == "overdue"
    assert result.primary_risk_level in {"medium", "high", "critical"}


def test_compute_patient_risk_aligns_with_high_risk_category():
    now = datetime(2026, 3, 2, 12, 0, 0)
    record = _record(diagnosis="普通复诊")
    result = compute_patient_risk(
        _patient(primary_category="high_risk"),
        records=[record],
        now=now,
    )

    assert result.primary_risk_level == "high"
    assert result.risk_score >= 70


# ── CVD risk-v2 tests ────────────────────────────────────────────────────────

def _cvd(**kwargs):
    return SimpleNamespace(**kwargs)


def test_compute_cvd_risk_ich_critical():
    rules = []
    level, score = _compute_cvd_risk(_cvd(ich_score=5, hunt_hess_grade=None, gcs_score=None, phases_score=None, mrs_score=None), rules)
    assert level == "critical"
    assert score >= 90
    assert any("ich_score_critical" in r for r in rules)


def test_compute_cvd_risk_ich_high():
    rules = []
    level, score = _compute_cvd_risk(_cvd(ich_score=3, hunt_hess_grade=None, gcs_score=None, phases_score=None, mrs_score=None), rules)
    assert level == "high"
    assert score >= 70


def test_compute_cvd_risk_hunt_hess_critical():
    rules = []
    level, score = _compute_cvd_risk(_cvd(ich_score=None, hunt_hess_grade=4, gcs_score=None, phases_score=None, mrs_score=None), rules)
    assert level == "critical"
    assert any("hunt_hess_critical" in r for r in rules)


def test_compute_cvd_risk_gcs_critical():
    rules = []
    level, score = _compute_cvd_risk(_cvd(ich_score=None, hunt_hess_grade=None, gcs_score=6, phases_score=None, mrs_score=None), rules)
    assert level == "critical"
    assert any("gcs_critical" in r for r in rules)


def test_compute_cvd_risk_phases_high():
    rules = []
    level, score = _compute_cvd_risk(_cvd(ich_score=None, hunt_hess_grade=None, gcs_score=None, phases_score=8, mrs_score=None), rules)
    assert level == "high"
    assert any("phases_high" in r for r in rules)


def test_compute_cvd_risk_mrs_high_dependency():
    rules = []
    level, score = _compute_cvd_risk(_cvd(ich_score=None, hunt_hess_grade=None, gcs_score=None, phases_score=None, mrs_score=5), rules)
    assert level == "high"
    assert any("mrs_high_dependency" in r for r in rules)


def test_compute_cvd_risk_no_data_returns_empty():
    rules = []
    level, score = _compute_cvd_risk(_cvd(ich_score=None, hunt_hess_grade=None, gcs_score=None, phases_score=None, mrs_score=None), rules)
    assert level == ""
    assert score == 0
    assert rules == []


def test_compute_patient_risk_cvd_overrides_keyword():
    """CVD rules should override keyword-based risk when cvd_contexts provided."""
    now = datetime(2026, 3, 2, 12, 0, 0)
    # Record has low-risk keyword, but CVD context shows critical
    record = _record(diagnosis="普通复诊")
    cvd = _cvd(ich_score=5, hunt_hess_grade=None, gcs_score=None, phases_score=None, mrs_score=None)
    result = compute_patient_risk(_patient(), records=[record], cvd_contexts=[cvd], now=now)
    assert result.primary_risk_level == "critical"
    assert "cvd_risk_computed" in result.risk_tags


def test_compute_patient_risk_falls_back_to_keywords_without_cvd():
    """Without cvd_contexts, keyword matching still works."""
    now = datetime(2026, 3, 2, 12, 0, 0)
    record = _record(diagnosis="急性心梗", follow_up_plan="两周复诊")
    result = compute_patient_risk(_patient(), records=[record], cvd_contexts=[], now=now)
    assert result.primary_risk_level == "high"
    assert "cvd_risk_computed" not in result.risk_tags
