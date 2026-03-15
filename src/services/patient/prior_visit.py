"""
复诊上下文：为随访病历结构化提供上次就诊的摘要参考。

Used by handle_add_record() when encounter_type == "follow_up" to inject
prior visit data into the LLM prompt so the AI generates a delta note
("变化") rather than repeating the complete history.
"""

from __future__ import annotations

from typing import Optional

from db.engine import AsyncSessionLocal
from utils.log import log


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


async def get_prior_visit_summary(
    doctor_id: str,
    patient_id: int,
) -> Optional[str]:
    """返回患者最近一次就诊的单行摘要（病历内容截取）。"""
    try:
        async with AsyncSessionLocal() as session:
            return await _fetch_record_snippet(session, doctor_id, patient_id)
    except Exception as exc:
        log(f"[PriorVisit] fetch failed for patient={patient_id}: {exc}")
    return None
