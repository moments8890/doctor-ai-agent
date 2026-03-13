"""
患者风险评估服务：基于病历和任务数据计算患者的随访优先级和风险等级。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

RULES_VERSION = "risk-v2"

_HIGH_RISK_KEYWORDS = [
    "急性", "STEMI", "心梗", "ACS", "休克", "恶性", "肿瘤", "化疗", "呼吸衰竭", "脑卒中",
]

_CRITICAL_RISK_KEYWORDS = [
    "心跳骤停", "呼吸骤停", "室颤", "心源性休克", "急诊PCI",
]

_DUE_SOON_DAYS = 3
_OVERDUE_DAYS = 14


@dataclass
class RiskResult:
    primary_risk_level: str
    risk_tags: List[str]
    risk_score: int
    follow_up_state: str
    rules_version: str
    computed_at: datetime
    matched_rules: List[str] = field(default_factory=list)


def _days_ago(dt: datetime, now: datetime) -> float:
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    return (now - dt).total_seconds() / 86400.0


def _record_has_follow_up(record: object) -> bool:
    import json
    tags_raw = getattr(record, "tags", None)
    if tags_raw:
        try:
            tags = json.loads(tags_raw)
            if any("随访" in t or "复诊" in t for t in tags):
                return True
        except Exception:
            pass
    content = getattr(record, "content", None) or ""
    return bool(content and ("随访" in content or "复诊" in content))


def _record_combined_text(record: object) -> str:
    import json
    content = getattr(record, "content", None) or ""
    tags_raw = getattr(record, "tags", None)
    tags: list = []
    if tags_raw:
        try:
            tags = json.loads(tags_raw)
        except Exception:
            pass
    return content + " " + " ".join(tags)


def _follow_up_state(records: List[object], now: datetime, matched_rules: List[str]) -> str:
    latest_with_plan = None
    for row in records:
        if _record_has_follow_up(row):
            latest_with_plan = row
            break

    if latest_with_plan is None:
        matched_rules.append("follow_up:not_needed")
        return "not_needed"

    days = _days_ago(latest_with_plan.created_at, now)
    if days > _OVERDUE_DAYS:
        matched_rules.append("follow_up:overdue")
        return "overdue"
    if days >= _DUE_SOON_DAYS:
        matched_rules.append("follow_up:due_soon")
        return "due_soon"

    matched_rules.append("follow_up:scheduled")
    return "scheduled"


def _apply_ich_score(cvd_ctx: object, level: str, score: int, matched_rules: List[str]) -> tuple:
    """ICH Score 0-6（30天死亡预测）对 level/score 的影响。"""
    ich = getattr(cvd_ctx, "ich_score", None)
    if ich is None:
        return level, score
    if ich >= 5:
        matched_rules.append("cvd:ich_score_critical(%d)" % ich)
        return "critical", 95
    if ich >= 3:
        matched_rules.append("cvd:ich_score_high(%d)" % ich)
        return "high", 75
    if ich >= 2:
        matched_rules.append("cvd:ich_score_medium(%d)" % ich)
        return "medium", 45
    return level, score


def _apply_hunt_hess(cvd_ctx: object, level: str, score: int, matched_rules: List[str]) -> tuple:
    """Hunt-Hess grade 1-5（SAH严重度）对 level/score 的影响。"""
    hh = getattr(cvd_ctx, "hunt_hess_grade", None)
    if hh is None:
        return level, score
    if hh >= 4 and level not in {"critical"}:
        matched_rules.append("cvd:hunt_hess_critical(%d)" % hh)
        return "critical", 95
    if hh == 3 and level not in {"critical", "high"}:
        matched_rules.append("cvd:hunt_hess_medium(%d)" % hh)
        return "medium", 50
    return level, score


def _apply_gcs(cvd_ctx: object, level: str, score: int, matched_rules: List[str]) -> tuple:
    """GCS 3-15（意识水平）对 level/score 的影响。"""
    gcs = getattr(cvd_ctx, "gcs_score", None)
    if gcs is None:
        return level, score
    if gcs <= 8 and level not in {"critical"}:
        matched_rules.append("cvd:gcs_critical(%d)" % gcs)
        return "critical", 95
    if gcs <= 12 and level not in {"critical", "high"}:
        matched_rules.append("cvd:gcs_high(%d)" % gcs)
        return "high", 70
    return level, score


def _apply_phases_mrs(cvd_ctx: object, level: str, score: int, matched_rules: List[str]) -> tuple:
    """PHASES 0-12（未破裂动脉瘤）和 mRS 0-6（功能依赖）对 level/score 的影响。"""
    phases = getattr(cvd_ctx, "phases_score", None)
    if phases is not None:
        if phases >= 7 and level not in {"critical", "high"}:
            level, score = "high", 70
            matched_rules.append("cvd:phases_high(%d)" % phases)
        elif phases >= 4 and level not in {"critical", "high", "medium"}:
            level, score = "medium", 45
            matched_rules.append("cvd:phases_medium(%d)" % phases)
    mrs = getattr(cvd_ctx, "mrs_score", None)
    if mrs is not None and mrs >= 4 and level not in {"critical"}:
        level = level if level == "high" else "high"
        score = max(score, 70)
        matched_rules.append("cvd:mrs_high_dependency(%d)" % mrs)
    return level, score


def _compute_cvd_risk(cvd_ctx: object, matched_rules: List[str]) -> tuple:
    """从 NeuroCVDContext 字段推导 (level, score)；无 CVD 数据时返回 ('', 0)。"""
    level, score = "", 0
    level, score = _apply_ich_score(cvd_ctx, level, score, matched_rules)
    level, score = _apply_hunt_hess(cvd_ctx, level, score, matched_rules)
    level, score = _apply_gcs(cvd_ctx, level, score, matched_rules)
    level, score = _apply_phases_mrs(cvd_ctx, level, score, matched_rules)
    return level, score


def _apply_keyword_risk(
    latest: object,
    now: datetime,
    level: str,
    score: int,
    tags: List[str],
    matched_rules: List[str],
) -> tuple:
    """关键词规则：基于最近病历文本判断风险等级。"""
    if latest is None:
        tags.append("no_records")
        matched_rules.append("risk:low:no_records")
        return level, score

    combined = _record_combined_text(latest)
    for kw in _CRITICAL_RISK_KEYWORDS:
        if kw in combined:
            tags.extend(["critical_keyword", "needs_immediate_action"])
            matched_rules.append("risk:critical_keyword=%s" % kw)
            return "critical", 95

    if any(kw in combined for kw in _HIGH_RISK_KEYWORDS):
        level, score = "high", 75
        tags.append("high_risk_keyword")
        matched_rules.append("risk:high_keyword")

    days_since_latest = _days_ago(latest.created_at, now)
    if days_since_latest > 120:
        score += 10
        tags.append("very_stale_record")
        matched_rules.append("risk:add_stale_record")
    if _record_has_follow_up(latest):
        score += 5
        tags.append("has_follow_up_plan")
        matched_rules.append("risk:add_follow_up_plan")
    if level == "low":
        if score >= 70:
            level = "high"
        elif score >= 40:
            level = "medium"
    return level, score


def compute_patient_risk(
    patient: object,
    records: List[object],
    cvd_contexts: Optional[List[object]] = None,
    now: Optional[datetime] = None,
) -> RiskResult:
    """计算患者随访优先级和风险等级（CVD 量表优先，无量表则关键词兜底）。"""
    if now is None:
        now = datetime.now(timezone.utc)

    matched_rules: List[str] = []
    tags: List[str] = []
    latest = records[0] if records else None
    score = 0
    level = "low"

    if cvd_contexts:
        cvd_level, cvd_score = _compute_cvd_risk(cvd_contexts[0], matched_rules)
        if cvd_level:
            level, score = cvd_level, cvd_score
            tags.append("cvd_risk_computed")

    if "cvd_risk_computed" not in tags:
        level, score = _apply_keyword_risk(latest, now, level, score, tags, matched_rules)

    follow_up_state = _follow_up_state(records, now, matched_rules)
    if follow_up_state == "overdue":
        tags.append("follow_up_overdue")
        if level == "low":
            level = "medium"
            score = max(score, 45)
            matched_rules.append("risk:upgrade_due_to_overdue")
    elif follow_up_state == "due_soon":
        tags.append("follow_up_due_soon")

    if getattr(patient, "primary_category", None) == "high_risk" and level in {"low", "medium"}:
        level = "high"
        score = max(score, 70)
        matched_rules.append("risk:align_with_category_high_risk")

    return RiskResult(
        primary_risk_level=level,
        risk_tags=tags,
        risk_score=score,
        follow_up_state=follow_up_state,
        rules_version=RULES_VERSION,
        computed_at=now,
        matched_rules=matched_rules,
    )


async def recompute_patient_risk(patient_id: int, session: AsyncSession) -> Optional[RiskResult]:
    from db.models import MedicalRecordDB, Patient
    from db.models.specialty import NeuroCVDContext

    result = await session.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        return None

    records_result = await session.execute(
        select(MedicalRecordDB)
        .where(
            MedicalRecordDB.patient_id == patient_id,
            MedicalRecordDB.doctor_id == patient.doctor_id,
        )
        .order_by(MedicalRecordDB.created_at.desc())
    )
    records = list(records_result.scalars().all())

    cvd_result = await session.execute(
        select(NeuroCVDContext)
        .where(NeuroCVDContext.patient_id == patient_id)
        .order_by(NeuroCVDContext.created_at.desc())
        .limit(5)
    )
    cvd_contexts = list(cvd_result.scalars().all())

    risk = compute_patient_risk(patient, records, cvd_contexts=cvd_contexts)
    # NOTE: Risk fields (primary_risk_level, risk_tags, risk_score,
    # follow_up_state) are NOT yet mapped on the Patient model.
    # Persist only when the schema is extended.  For now, return the
    # computed result for callers to use in-memory.
    return risk
