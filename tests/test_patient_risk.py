from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from services.patient.patient_risk import compute_patient_risk


def _patient(**kwargs):
    data = {
        "created_at": datetime(2026, 1, 1, 0, 0, 0),
        "primary_category": "new",
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def _record(**kwargs):
    data = {
        "created_at": datetime(2026, 3, 1, 10, 0, 0),
        "diagnosis": "高血压",
        "follow_up_plan": None,
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
