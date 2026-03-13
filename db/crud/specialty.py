"""专科临床上下文表的 CRUD 辅助函数：神经外科 CVD 数据的读写与更新。"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.neuro_case import NeuroCVDSurgicalContext
from db.models.specialty import NeuroCVDContext
from utils.log import log


def _parse_cvd_json(row: NeuroCVDContext) -> Optional[NeuroCVDSurgicalContext]:
    """Deserialize raw_json back to the Pydantic model. Returns None if empty."""
    if not row.raw_json:
        return None
    try:
        return NeuroCVDSurgicalContext.model_validate(json.loads(row.raw_json))
    except Exception:
        return None


async def save_cvd_context(
    session: AsyncSession,
    doctor_id: str,
    patient_id: Optional[int],
    record_id: int,
    ctx: NeuroCVDSurgicalContext,
    source: str = "chat",
    commit: bool = True,
) -> NeuroCVDContext:
    """Persist a NeuroCVDSurgicalContext to neuro_cvd_context."""
    row = NeuroCVDContext(
        doctor_id=doctor_id,
        patient_id=patient_id,
        record_id=record_id,
        diagnosis_subtype=ctx.diagnosis_subtype,
        surgery_status=ctx.surgery_status,
        source=source,
        raw_json=json.dumps(ctx.model_dump(exclude_none=True), ensure_ascii=False),
    )
    session.add(row)
    if commit:
        await session.commit()
        await session.refresh(row)
    else:
        await session.flush()
    log(f"[silent-save] cvd_context saved doctor={doctor_id} patient_id={patient_id} record_id={record_id} source={source!r} subtype={ctx.diagnosis_subtype!r}")
    return row


async def get_cvd_context_for_patient(
    session: AsyncSession,
    doctor_id: str,
    patient_id: int,
) -> Optional[NeuroCVDContext]:
    """Return the most recent NeuroCVDContext row for a patient."""
    result = await session.execute(
        select(NeuroCVDContext)
        .where(
            NeuroCVDContext.doctor_id == doctor_id,
            NeuroCVDContext.patient_id == patient_id,
        )
        .order_by(NeuroCVDContext.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
