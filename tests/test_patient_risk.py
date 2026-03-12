"""Unit tests for services/patient/patient_risk.py — risk scoring and stratification."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.patient.patient_risk import (
    RiskResult,
    _apply_gcs,
    _apply_hunt_hess,
    _apply_ich_score,
    _apply_keyword_risk,
    _apply_phases_mrs,
    _compute_cvd_risk,
    _days_ago,
    _follow_up_state,
    _record_combined_text,
    _record_has_follow_up,
    compute_patient_risk,
    recompute_patient_risk,
)

NOW = datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc)


def _rec(content: str = "", tags: Optional[str] = None, days_old: int = 0):
    """Create a mock record with content, tags (JSON string), and created_at."""
    return SimpleNamespace(
        content=content,
        tags=tags,
        created_at=NOW - timedelta(days=days_old),
    )


def _patient(primary_category: Optional[str] = None):
    return SimpleNamespace(primary_category=primary_category)


def _cvd(**kwargs):
    return SimpleNamespace(**kwargs)


# ---------------------------------------------------------------------------
# _days_ago
# ---------------------------------------------------------------------------
class TestDaysAgo:
    def test_same_datetime(self):
        assert _days_ago(NOW, NOW) == 0.0

    def test_positive_days(self):
        past = NOW - timedelta(days=10)
        assert abs(_days_ago(past, NOW) - 10.0) < 0.001

    def test_strips_tzinfo(self):
        aware = datetime(2026, 3, 1, tzinfo=timezone.utc)
        naive = datetime(2026, 3, 11)
        result = _days_ago(aware, naive)
        assert abs(result - 10.0) < 0.001


# ---------------------------------------------------------------------------
# _record_has_follow_up
# ---------------------------------------------------------------------------
class TestRecordHasFollowUp:
    def test_follow_up_in_tags(self):
        r = _rec(tags=json.dumps(["随访一周"]))
        assert _record_has_follow_up(r) is True

    def test_revisit_in_tags(self):
        r = _rec(tags=json.dumps(["复诊安排"]))
        assert _record_has_follow_up(r) is True

    def test_follow_up_in_content(self):
        r = _rec(content="建议一周后随访")
        assert _record_has_follow_up(r) is True

    def test_revisit_in_content(self):
        r = _rec(content="两周后复诊")
        assert _record_has_follow_up(r) is True

    def test_no_follow_up(self):
        r = _rec(content="一般检查", tags=json.dumps(["血常规"]))
        assert _record_has_follow_up(r) is False

    def test_invalid_json_tags_falls_back_to_content(self):
        r = _rec(content="随访", tags="not json")
        assert _record_has_follow_up(r) is True

    def test_none_tags_none_content(self):
        r = SimpleNamespace(tags=None, content=None)
        assert _record_has_follow_up(r) is False

    def test_empty_content_no_tags(self):
        r = SimpleNamespace(tags=None, content="")
        assert _record_has_follow_up(r) is False


# ---------------------------------------------------------------------------
# _record_combined_text
# ---------------------------------------------------------------------------
class TestRecordCombinedText:
    def test_combines_content_and_tags(self):
        r = _rec(content="胸痛", tags=json.dumps(["冠心病", "PCI"]))
        result = _record_combined_text(r)
        assert "胸痛" in result
        assert "冠心病" in result
        assert "PCI" in result

    def test_none_content_and_tags(self):
        r = SimpleNamespace(content=None, tags=None)
        result = _record_combined_text(r)
        assert isinstance(result, str)

    def test_invalid_json_tags(self):
        r = _rec(content="test", tags="bad json")
        result = _record_combined_text(r)
        assert "test" in result


# ---------------------------------------------------------------------------
# _follow_up_state
# ---------------------------------------------------------------------------
class TestFollowUpState:
    def test_no_records_with_follow_up(self):
        rules: List[str] = []
        result = _follow_up_state([_rec(content="一般检查")], NOW, rules)
        assert result == "not_needed"
        assert "follow_up:not_needed" in rules

    def test_empty_records(self):
        rules: List[str] = []
        result = _follow_up_state([], NOW, rules)
        assert result == "not_needed"

    def test_overdue(self):
        rules: List[str] = []
        r = _rec(content="随访", days_old=15)
        result = _follow_up_state([r], NOW, rules)
        assert result == "overdue"
        assert "follow_up:overdue" in rules

    def test_due_soon(self):
        rules: List[str] = []
        r = _rec(content="随访", days_old=5)
        result = _follow_up_state([r], NOW, rules)
        assert result == "due_soon"
        assert "follow_up:due_soon" in rules

    def test_scheduled(self):
        rules: List[str] = []
        r = _rec(content="随访", days_old=1)
        result = _follow_up_state([r], NOW, rules)
        assert result == "scheduled"
        assert "follow_up:scheduled" in rules


# ---------------------------------------------------------------------------
# _apply_ich_score
# ---------------------------------------------------------------------------
class TestApplyIchScore:
    def test_none_ich(self):
        ctx = _cvd()
        level, score = _apply_ich_score(ctx, "low", 10, [])
        assert level == "low"
        assert score == 10

    def test_critical_ich(self):
        rules: List[str] = []
        ctx = _cvd(ich_score=5)
        level, score = _apply_ich_score(ctx, "low", 10, rules)
        assert level == "critical"
        assert score == 95
        assert any("ich_score_critical" in r for r in rules)

    def test_high_ich(self):
        rules: List[str] = []
        ctx = _cvd(ich_score=3)
        level, score = _apply_ich_score(ctx, "low", 10, rules)
        assert level == "high"
        assert score == 75

    def test_medium_ich(self):
        rules: List[str] = []
        ctx = _cvd(ich_score=2)
        level, score = _apply_ich_score(ctx, "low", 10, rules)
        assert level == "medium"
        assert score == 45

    def test_low_ich(self):
        ctx = _cvd(ich_score=1)
        level, score = _apply_ich_score(ctx, "low", 10, [])
        assert level == "low"
        assert score == 10


# ---------------------------------------------------------------------------
# _apply_hunt_hess
# ---------------------------------------------------------------------------
class TestApplyHuntHess:
    def test_none_hh(self):
        ctx = _cvd()
        level, score = _apply_hunt_hess(ctx, "low", 10, [])
        assert level == "low"

    def test_critical_hh(self):
        rules: List[str] = []
        ctx = _cvd(hunt_hess_grade=4)
        level, score = _apply_hunt_hess(ctx, "low", 10, rules)
        assert level == "critical"
        assert score == 95

    def test_hh_5_also_critical(self):
        ctx = _cvd(hunt_hess_grade=5)
        level, score = _apply_hunt_hess(ctx, "low", 10, [])
        assert level == "critical"

    def test_hh_3_medium(self):
        rules: List[str] = []
        ctx = _cvd(hunt_hess_grade=3)
        level, score = _apply_hunt_hess(ctx, "low", 10, rules)
        assert level == "medium"
        assert score == 50

    def test_hh_4_skips_if_already_critical(self):
        ctx = _cvd(hunt_hess_grade=4)
        level, score = _apply_hunt_hess(ctx, "critical", 95, [])
        assert level == "critical"  # unchanged

    def test_hh_3_skips_if_already_high(self):
        ctx = _cvd(hunt_hess_grade=3)
        level, score = _apply_hunt_hess(ctx, "high", 75, [])
        assert level == "high"  # unchanged

    def test_hh_2_no_change(self):
        ctx = _cvd(hunt_hess_grade=2)
        level, score = _apply_hunt_hess(ctx, "low", 10, [])
        assert level == "low"


# ---------------------------------------------------------------------------
# _apply_gcs
# ---------------------------------------------------------------------------
class TestApplyGcs:
    def test_none_gcs(self):
        ctx = _cvd()
        level, score = _apply_gcs(ctx, "low", 10, [])
        assert level == "low"

    def test_gcs_le_8_critical(self):
        rules: List[str] = []
        ctx = _cvd(gcs_score=7)
        level, score = _apply_gcs(ctx, "low", 10, rules)
        assert level == "critical"
        assert score == 95
        assert any("gcs_critical" in r for r in rules)

    def test_gcs_8_critical(self):
        ctx = _cvd(gcs_score=8)
        level, score = _apply_gcs(ctx, "low", 10, [])
        assert level == "critical"

    def test_gcs_le_12_high(self):
        rules: List[str] = []
        ctx = _cvd(gcs_score=10)
        level, score = _apply_gcs(ctx, "low", 10, rules)
        assert level == "high"
        assert score == 70

    def test_gcs_skips_if_already_critical(self):
        ctx = _cvd(gcs_score=7)
        level, score = _apply_gcs(ctx, "critical", 95, [])
        assert level == "critical"

    def test_gcs_12_skips_if_already_high(self):
        ctx = _cvd(gcs_score=12)
        level, score = _apply_gcs(ctx, "high", 75, [])
        assert level == "high"

    def test_gcs_13_no_change(self):
        ctx = _cvd(gcs_score=13)
        level, score = _apply_gcs(ctx, "low", 10, [])
        assert level == "low"


# ---------------------------------------------------------------------------
# _apply_phases_mrs
# ---------------------------------------------------------------------------
class TestApplyPhasesMrs:
    def test_no_phases_no_mrs(self):
        ctx = _cvd()
        level, score = _apply_phases_mrs(ctx, "low", 10, [])
        assert level == "low"

    def test_phases_ge_7_high(self):
        rules: List[str] = []
        ctx = _cvd(phases_score=7)
        level, score = _apply_phases_mrs(ctx, "low", 10, rules)
        assert level == "high"
        assert score == 70
        assert any("phases_high" in r for r in rules)

    def test_phases_ge_4_medium(self):
        rules: List[str] = []
        ctx = _cvd(phases_score=4)
        level, score = _apply_phases_mrs(ctx, "low", 10, rules)
        assert level == "medium"
        assert score == 45

    def test_phases_3_no_change(self):
        ctx = _cvd(phases_score=3)
        level, score = _apply_phases_mrs(ctx, "low", 10, [])
        assert level == "low"

    def test_phases_ge_7_skips_if_critical(self):
        ctx = _cvd(phases_score=7)
        level, score = _apply_phases_mrs(ctx, "critical", 95, [])
        assert level == "critical"

    def test_phases_ge_4_skips_if_high(self):
        ctx = _cvd(phases_score=5)
        level, score = _apply_phases_mrs(ctx, "high", 75, [])
        assert level == "high"

    def test_mrs_ge_4_upgrades(self):
        rules: List[str] = []
        ctx = _cvd(mrs_score=4)
        level, score = _apply_phases_mrs(ctx, "low", 10, rules)
        assert level == "high"
        assert score >= 70
        assert any("mrs_high_dependency" in r for r in rules)

    def test_mrs_ge_4_keeps_high_if_already_high(self):
        ctx = _cvd(mrs_score=5)
        level, score = _apply_phases_mrs(ctx, "high", 75, [])
        assert level == "high"
        assert score >= 70

    def test_mrs_skips_if_critical(self):
        ctx = _cvd(mrs_score=5)
        level, score = _apply_phases_mrs(ctx, "critical", 95, [])
        assert level == "critical"

    def test_mrs_below_4_no_change(self):
        ctx = _cvd(mrs_score=3)
        level, score = _apply_phases_mrs(ctx, "low", 10, [])
        assert level == "low"


# ---------------------------------------------------------------------------
# _compute_cvd_risk
# ---------------------------------------------------------------------------
class TestComputeCvdRisk:
    def test_empty_cvd(self):
        ctx = _cvd()
        rules: List[str] = []
        level, score = _compute_cvd_risk(ctx, rules)
        assert level == ""
        assert score == 0

    def test_ich_propagates(self):
        ctx = _cvd(ich_score=5)
        rules: List[str] = []
        level, score = _compute_cvd_risk(ctx, rules)
        assert level == "critical"

    def test_combined_scores(self):
        ctx = _cvd(ich_score=2, mrs_score=5)
        rules: List[str] = []
        level, score = _compute_cvd_risk(ctx, rules)
        # ich_score=2 -> medium/45, then mrs>=4 upgrades to high/70
        assert level == "high"
        assert score >= 70


# ---------------------------------------------------------------------------
# _apply_keyword_risk
# ---------------------------------------------------------------------------
class TestApplyKeywordRisk:
    def test_no_latest_record(self):
        tags: List[str] = []
        rules: List[str] = []
        level, score = _apply_keyword_risk(None, NOW, "low", 0, tags, rules)
        assert "no_records" in tags
        assert "risk:low:no_records" in rules

    def test_critical_keyword(self):
        r = _rec(content="患者心跳骤停")
        tags: List[str] = []
        rules: List[str] = []
        level, score = _apply_keyword_risk(r, NOW, "low", 0, tags, rules)
        assert level == "critical"
        assert score == 95
        assert "critical_keyword" in tags

    def test_high_keyword(self):
        r = _rec(content="急性心梗 STEMI")
        tags: List[str] = []
        rules: List[str] = []
        level, score = _apply_keyword_risk(r, NOW, "low", 0, tags, rules)
        assert level == "high"
        assert score == 75
        assert "high_risk_keyword" in tags

    def test_stale_record_adds_score(self):
        r = _rec(content="一般检查", days_old=130)
        tags: List[str] = []
        rules: List[str] = []
        level, score = _apply_keyword_risk(r, NOW, "low", 0, tags, rules)
        assert "very_stale_record" in tags
        assert score >= 10

    def test_follow_up_plan_adds_score(self):
        r = _rec(content="建议随访")
        tags: List[str] = []
        rules: List[str] = []
        level, score = _apply_keyword_risk(r, NOW, "low", 0, tags, rules)
        assert "has_follow_up_plan" in tags
        assert score >= 5

    def test_low_level_upgraded_to_medium_on_high_score(self):
        # Stale + follow_up = 15 points, not enough for medium (40).
        # But with a high keyword, it's 75+5+10=90 -> high already
        r = _rec(content="急性心梗 随访", days_old=130)
        tags: List[str] = []
        rules: List[str] = []
        level, score = _apply_keyword_risk(r, NOW, "low", 0, tags, rules)
        assert level == "high"


# ---------------------------------------------------------------------------
# compute_patient_risk (integration of all sub-functions)
# ---------------------------------------------------------------------------
class TestComputePatientRisk:
    def test_low_risk_no_records(self):
        p = _patient()
        result = compute_patient_risk(p, [], now=NOW)
        assert result.primary_risk_level == "low"
        assert "no_records" in result.risk_tags
        assert result.rules_version == "risk-v2"

    def test_critical_keyword_takes_precedence(self):
        p = _patient()
        r = _rec(content="患者室颤发作")
        result = compute_patient_risk(p, [r], now=NOW)
        assert result.primary_risk_level == "critical"
        assert result.risk_score == 95

    def test_cvd_context_used_over_keywords(self):
        p = _patient()
        r = _rec(content="急性心梗 STEMI")  # high keyword
        ctx = _cvd(ich_score=5)  # critical CVD
        result = compute_patient_risk(p, [r], cvd_contexts=[ctx], now=NOW)
        assert result.primary_risk_level == "critical"
        assert "cvd_risk_computed" in result.risk_tags

    def test_overdue_follow_up_upgrades_low(self):
        p = _patient()
        r = _rec(content="建议随访", days_old=20)
        result = compute_patient_risk(p, [r], now=NOW)
        assert "follow_up_overdue" in result.risk_tags
        # The keyword risk already has "has_follow_up_plan" (+5),
        # plus overdue upgrades low to medium
        assert result.primary_risk_level in ("medium", "high")

    def test_due_soon_tag_present(self):
        p = _patient()
        r = _rec(content="建议随访", days_old=4)
        result = compute_patient_risk(p, [r], now=NOW)
        assert "follow_up_due_soon" in result.risk_tags

    def test_high_risk_category_upgrades_low(self):
        p = _patient(primary_category="high_risk")
        r = _rec(content="一般检查")
        result = compute_patient_risk(p, [r], now=NOW)
        assert result.primary_risk_level == "high"
        assert result.risk_score >= 70
        assert "risk:align_with_category_high_risk" in result.matched_rules

    def test_high_risk_category_upgrades_medium(self):
        p = _patient(primary_category="high_risk")
        r = _rec(content="一般检查 随访", days_old=20)  # overdue -> medium
        result = compute_patient_risk(p, [r], now=NOW)
        assert result.primary_risk_level == "high"

    def test_defaults_to_utcnow(self):
        p = _patient()
        result = compute_patient_risk(p, [])
        assert result.computed_at is not None
        assert result.primary_risk_level == "low"

    def test_cvd_empty_level_falls_back_to_keywords(self):
        """When CVD ctx has no scoring fields, keyword path is used."""
        p = _patient()
        r = _rec(content="急性心梗")
        ctx = _cvd()  # no CVD scores at all => level=""
        result = compute_patient_risk(p, [r], cvd_contexts=[ctx], now=NOW)
        # empty cvd_level means "cvd_risk_computed" is NOT added, so keywords run
        assert "cvd_risk_computed" not in result.risk_tags
        assert result.primary_risk_level == "high"


# ---------------------------------------------------------------------------
# recompute_patient_risk (async DB path)
# ---------------------------------------------------------------------------
class TestRecomputePatientRisk:
    @pytest.mark.asyncio
    async def test_returns_none_when_patient_not_found(self):
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await recompute_patient_risk(999, session)
        assert result is None

    @pytest.mark.asyncio
    async def test_computes_and_persists_risk(self):
        patient = SimpleNamespace(
            id=1, name="张三", doctor_id="doc1", gender="男",
            year_of_birth=1990, primary_category=None,
            primary_risk_level=None, risk_tags=None,
            risk_score=None, follow_up_state=None,
        )
        record = SimpleNamespace(
            content="一般检查", tags=None,
            created_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
            patient_id=1, doctor_id="doc1",
        )

        # Build mock results for three execute calls
        patient_result = MagicMock()
        patient_result.scalar_one_or_none.return_value = patient

        records_scalars = MagicMock()
        records_scalars.all.return_value = [record]
        records_result = MagicMock()
        records_result.scalars.return_value = records_scalars

        cvd_scalars = MagicMock()
        cvd_scalars.all.return_value = []
        cvd_result = MagicMock()
        cvd_result.scalars.return_value = cvd_scalars

        session = AsyncMock()
        session.execute.side_effect = [patient_result, records_result, cvd_result]

        result = await recompute_patient_risk(1, session)
        assert result is not None
        assert result.primary_risk_level == "low"
        assert patient.primary_risk_level == "low"
        session.commit.assert_awaited_once()
