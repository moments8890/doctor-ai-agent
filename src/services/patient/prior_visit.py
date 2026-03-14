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


async def _fetch_cvd_summary(session: object, doctor_id: str, patient_id: int) -> Optional[str]:
    """查询最近一条 CVD 量表记录并格式化为摘要行；无数据时返回 None。"""
    from sqlalchemy import select
    from db.models.specialty import NeuroCVDContext
    cvd_result = await session.execute(
        select(NeuroCVDContext)
        .where(NeuroCVDContext.doctor_id == doctor_id, NeuroCVDContext.patient_id == patient_id)
        .order_by(NeuroCVDContext.created_at.desc())
        .limit(1)
    )
    cvd_row = cvd_result.scalar_one_or_none()
    if not cvd_row:
        return None
    visit_date = cvd_row.created_at.strftime("%Y-%m-%d") if cvd_row.created_at else None
    return _format_cvd_summary(cvd_row.raw_json, visit_date)


async def _fetch_record_snippet(session: object, doctor_id: str, patient_id: int) -> Optional[str]:
    """查询最近一条病历内容并截取为摘要行；无数据时返回 None。"""
    from sqlalchemy import select
    from db.models.records import MedicalRecordDB
    rec_result = await session.execute(
        select(MedicalRecordDB)
        .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id == patient_id)
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(1)
    )
    rec = rec_result.scalar_one_or_none()
    if rec and rec.content:
        date_str = rec.created_at.strftime("%Y-%m-%d") if rec.created_at else ""
        snippet = rec.content[:120].rstrip()
        return f"上次就诊（{date_str}）：{snippet}{'…' if len(rec.content) > 120 else ''}"
    return None


async def _fetch_latest_scores_summary(
    session: object, doctor_id: str, patient_id: int,
) -> Optional[str]:
    """Fetch specialty scores from the most recent record and format as summary."""
    from sqlalchemy import select
    from db.models.records import MedicalRecordDB
    from db.crud.scores import get_scores_for_records

    rec_result = await session.execute(
        select(MedicalRecordDB.id)
        .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id == patient_id)
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(3)
    )
    rec_ids = [row[0] for row in rec_result.all()]
    if not rec_ids:
        return None
    scores_map = await get_scores_for_records(session, rec_ids, doctor_id)
    if not scores_map:
        return None
    # Collect unique score types from most recent records
    seen: dict[str, str] = {}
    for rid in rec_ids:
        for s in scores_map.get(rid, []):
            if s.score_type not in seen:
                val = f"{s.score_value:g}" if s.score_value is not None else (s.raw_text or "?")
                seen[s.score_type] = f"{s.score_type}={val}"
    if not seen:
        return None
    return "最近量表：" + "，".join(seen.values())


async def get_prior_visit_summary(
    doctor_id: str,
    patient_id: int,
) -> Optional[str]:
    """返回患者最近一次就诊的单行摘要（CVD 量表优先，其次专科量表，其次病历内容截取）。"""
    try:
        async with AsyncSessionLocal() as session:
            cvd_summary = await _fetch_cvd_summary(session, doctor_id, patient_id)
            scores_summary = await _fetch_latest_scores_summary(session, doctor_id, patient_id)
            if cvd_summary and scores_summary:
                return f"{cvd_summary}；{scores_summary}"
            if cvd_summary:
                return cvd_summary
            if scores_summary:
                return scores_summary
            return await _fetch_record_snippet(session, doctor_id, patient_id)
    except Exception as exc:
        log(f"[PriorVisit] fetch failed for patient={patient_id}: {exc}")
    return None
