"""
复诊上下文：为随访病历结构化提供上次就诊的量表/摘要参考。

Used by handle_add_record() when encounter_type == "follow_up" to inject
prior visit data into the LLM prompt so the AI generates a delta note
("变化") rather than repeating the complete history.
"""

from __future__ import annotations

import json
from typing import Optional

from db.engine import AsyncSessionLocal
from utils.log import log

# CVD fields to surface in the prior-visit summary (display name → raw_json key)
_CVD_DISPLAY_FIELDS: list[tuple[str, str]] = [
    ("ICH Score", "ich_score"),
    ("Hunt-Hess", "hunt_hess_grade"),
    ("Fisher", "fisher_grade"),
    ("GCS", "gcs_score"),
    ("NIHSS", "nihss_score"),
    ("mRS", "mrs_score"),
    ("PHASES", "phases_score"),
    ("Spetzler-Martin", "spetzler_martin_grade"),
    ("Suzuki", "suzuki_stage"),
    ("Barthel", "barthel_index"),
]


def _format_cvd_summary(raw_json_str: Optional[str], visit_date: Optional[str]) -> Optional[str]:
    """Format key CVD scores from a raw_json string into a brief summary line."""
    if not raw_json_str:
        return None
    try:
        data = json.loads(raw_json_str)
    except Exception:
        return None

    parts: list[str] = []
    for label, key in _CVD_DISPLAY_FIELDS:
        val = data.get(key)
        if val is not None:
            parts.append(f"{label}={val}")

    surgery = data.get("surgery_status")
    if surgery:
        parts.append(f"手术状态={surgery}")

    subtype = data.get("diagnosis_subtype")
    if subtype:
        parts.append(f"病种={subtype}")

    if not parts:
        return None

    date_str = f"（{visit_date}）" if visit_date else ""
    return f"上次量表{date_str}：" + "，".join(parts)


async def get_prior_visit_summary(
    doctor_id: str,
    patient_id: int,
) -> Optional[str]:
    """Return a one-line summary of the patient's most recent visit for follow-up context.

    Priority:
    1. Most recent neuro_cvd_context row (CVD patients) — key scores
    2. Most recent medical_record content snippet (all patients)

    Returns None if no data found or on any DB error.
    """
    try:
        from sqlalchemy import select
        from db.models.specialty import NeuroCVDContext
        from db.models.records import MedicalRecordDB

        async with AsyncSessionLocal() as session:
            # 1. Try CVD context first
            cvd_result = await session.execute(
                select(NeuroCVDContext)
                .where(
                    NeuroCVDContext.doctor_id == doctor_id,
                    NeuroCVDContext.patient_id == patient_id,
                )
                .order_by(NeuroCVDContext.created_at.desc())
                .limit(1)
            )
            cvd_row = cvd_result.scalar_one_or_none()

            if cvd_row:
                visit_date = cvd_row.created_at.strftime("%Y-%m-%d") if cvd_row.created_at else None
                summary = _format_cvd_summary(cvd_row.raw_json, visit_date)
                if summary:
                    return summary

            # 2. Fall back to last record content snippet
            rec_result = await session.execute(
                select(MedicalRecordDB)
                .where(
                    MedicalRecordDB.doctor_id == doctor_id,
                    MedicalRecordDB.patient_id == patient_id,
                )
                .order_by(MedicalRecordDB.created_at.desc())
                .limit(1)
            )
            rec = rec_result.scalar_one_or_none()
            if rec and rec.content:
                date_str = rec.created_at.strftime("%Y-%m-%d") if rec.created_at else ""
                snippet = rec.content[:120].rstrip()
                return f"上次就诊（{date_str}）：{snippet}{'…' if len(rec.content) > 120 else ''}"

    except Exception as exc:
        log(f"[PriorVisit] fetch failed for patient={patient_id}: {exc}")

    return None
