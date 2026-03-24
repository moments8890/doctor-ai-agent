"""
患者分类服务：基于病历内容自动将患者划分为慢病、急症等类别。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

RULES_VERSION = "v1"

HIGH_RISK_KEYWORDS: List[str] = [
    "急性", "STEMI", "心梗", "心衰", "ACS", "肿瘤", "化疗", "不稳定型", "恶性",
]

# Thresholds in days
_RECENT_VISIT_DAYS = 14
_ACTIVE_FOLLOWUP_DAYS = 30
_STABLE_THRESHOLD_DAYS = 30
_NEW_PATIENT_DAYS = 7
_NO_RECENT_VISIT_DAYS = 90


@dataclass
class CategoryResult:
    primary_category: str
    category_tags: List[str]
    rules_version: str
    computed_at: datetime
    matched_rules: List[str] = field(default_factory=list)


def _days_ago(dt: datetime, now: datetime) -> float:
    """Return how many days ago *dt* was relative to *now* (both naive UTC)."""
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    return (now - dt).total_seconds() / 86400.0


def categorize_patient(
    patient: object,
    records: list,
    now: Optional[datetime] = None,
) -> CategoryResult:
    """Pure function — no I/O.

    *patient* must expose: ``created_at`` (datetime).
    Each item in *records* must expose: ``created_at`` (datetime),
    ``diagnosis`` (Optional[str]), ``follow_up_plan`` (Optional[str]).
    Records are assumed to be ordered newest-first.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    matched_rules: List[str] = []
    tags: List[str] = []

    # ------------------------------------------------------------------ tags
    latest = records[0] if records else None

    if latest is not None:
        days_since = _days_ago(latest.created_at, now)

        if days_since <= _RECENT_VISIT_DAYS:
            tags.append("recent_visit")

        if days_since > _NO_RECENT_VISIT_DAYS:
            tags.append("no_recent_visit")

        if days_since > _STABLE_THRESHOLD_DAYS:
            tags.append("needs_record_update")
    else:
        # No records at all — if old enough, mark as no_recent_visit
        patient_days = _days_ago(patient.created_at, now)
        if patient_days > _NO_RECENT_VISIT_DAYS:
            tags.append("no_recent_visit")

    # ------------------------------------------------------------------ primary category (precedence order)
    primary = _determine_primary(patient, records, latest, now, matched_rules)

    return CategoryResult(
        primary_category=primary,
        category_tags=tags,
        rules_version=RULES_VERSION,
        computed_at=now,
        matched_rules=matched_rules,
    )


def _record_text(record: object) -> str:
    """Return combined searchable text from a record's content and tags."""
    content = getattr(record, "content", None) or ""
    tags_raw = getattr(record, "tags", None)
    tags: List[str] = []
    if tags_raw:
        try:
            tags = json.loads(tags_raw)
        except Exception:
            pass
    return content + " " + " ".join(tags)


def _record_has_follow_up(record: object) -> bool:
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


def _determine_primary(
    patient: object,
    records: list,
    latest: object,
    now: datetime,
    matched_rules: List[str],
) -> str:
    # Priority 1: high_risk — latest record content/tags contain high-risk keyword
    if latest is not None:
        combined = _record_text(latest)
        for kw in HIGH_RISK_KEYWORDS:
            if kw in combined:
                matched_rules.append(f"high_risk:keyword={kw}")
                return "high_risk"

    # Priority 2: active_followup — has follow-up intent AND last record ≤ 30 days
    if latest is not None and _record_has_follow_up(latest):
        days_since = _days_ago(latest.created_at, now)
        if days_since <= _ACTIVE_FOLLOWUP_DAYS:
            matched_rules.append(f"active_followup:days_since={days_since:.1f}")
            return "active_followup"

    # Priority 3: stable — has records AND last record > 30 days ago
    if records:
        days_since = _days_ago(latest.created_at, now)
        if days_since > _STABLE_THRESHOLD_DAYS:
            matched_rules.append(f"stable:days_since={days_since:.1f}")
            return "stable"

    # Priority 4: new — no records OR patient created within 7 days
    patient_days = _days_ago(patient.created_at, now)
    if not records or patient_days <= _NEW_PATIENT_DAYS:
        matched_rules.append(f"new:patient_days={patient_days:.1f},has_records={bool(records)}")
        return "new"

    # Fallback (should not normally be reached, covers edge cases)
    matched_rules.append("new:fallback")
    return "new"


async def recompute_patient_category(
    patient_id: int,
    session: AsyncSession,
    *,
    commit: bool = True,
) -> None:
    """Load patient + records, compute category, persist result."""
    from db.models import Patient, MedicalRecordDB  # avoid circular at module level

    patient_result = await session.execute(
        select(Patient).where(Patient.id == patient_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient is None:
        return

    records_result = await session.execute(
        select(MedicalRecordDB)
        .where(
            MedicalRecordDB.patient_id == patient_id,
            MedicalRecordDB.doctor_id == patient.doctor_id,
        )
        .order_by(MedicalRecordDB.created_at.desc())
    )
    records = list(records_result.scalars().all())

    result = categorize_patient(patient, records)

    # TODO: primary_category and category_tags columns removed from Patient model;
    # persist categorization results to a separate table if still needed.
    _ = result  # computed but not persisted
    if commit:
        pass  # nothing to commit
    else:
        pass  # nothing to flush


async def recompute_all_categories(
    session: AsyncSession,
    doctor_id: Optional[str] = None,
    batch_size: int = 100,
) -> dict:
    """Recompute categories for all (or one doctor's) patients.

    Returns a summary dict with ``total``, ``changed``, ``errors``.
    """
    from db.models import Patient, MedicalRecordDB  # avoid circular at module level

    query = select(Patient)
    if doctor_id is not None:
        query = query.where(Patient.doctor_id == doctor_id)

    result = await session.execute(query)
    patients = list(result.scalars().all())

    total = len(patients)
    changed = 0
    errors = 0

    for i in range(0, total, batch_size):
        batch = patients[i : i + batch_size]
        for patient in batch:
            try:
                records_result = await session.execute(
                    select(MedicalRecordDB)
                    .where(
                        MedicalRecordDB.patient_id == patient.id,
                        MedicalRecordDB.doctor_id == patient.doctor_id,
                    )
                    .order_by(MedicalRecordDB.created_at.desc())
                )
                records = list(records_result.scalars().all())

                cat_result = categorize_patient(patient, records)

                # TODO: primary_category and category_tags removed from Patient;
                # persist to a separate table if categorization is still needed.
                _ = cat_result  # computed but not persisted
            except Exception:  # noqa: BLE001
                errors += 1

        await session.commit()

    return {"total": total, "changed": changed, "errors": errors}
