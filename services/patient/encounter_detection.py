"""
就诊类型检测：基于患者历史记录和输入文本，判断本次就诊为初诊还是复诊。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.records import MedicalRecordDB

_FOLLOW_UP_KEYWORDS = {"复诊", "随访", "复查", "回诊", "复来", "复往"}
_FIRST_VISIT_KEYWORDS = {"初诊", "首诊", "新患者", "第一次", "新病人"}


async def detect_encounter_type(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int | None,
    text: str,
) -> str:
    """
    Return 'first_visit', 'follow_up', or 'unknown'.

    Rules (in priority order):
    1. Explicit first-visit keywords in text → first_visit
    2. Explicit follow-up keywords in text → follow_up
    3. No prior records for this patient under this doctor → first_visit
    4. Prior records exist → follow_up
    5. No patient_id known → unknown
    """
    # Keyword fast-path
    for kw in _FIRST_VISIT_KEYWORDS:
        if kw in text:
            return "first_visit"
    for kw in _FOLLOW_UP_KEYWORDS:
        if kw in text:
            return "follow_up"

    if patient_id is None:
        return "unknown"

    result = await session.execute(
        select(MedicalRecordDB.id)
        .where(
            MedicalRecordDB.patient_id == patient_id,
            MedicalRecordDB.doctor_id == doctor_id,
        )
        .limit(1)
    )
    has_prior = result.scalar_one_or_none() is not None
    return "follow_up" if has_prior else "first_visit"
