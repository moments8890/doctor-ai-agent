"""CRUD helpers for specialty clinical context tables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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
    await session.commit()
    await session.refresh(row)
    log(f"[silent-save] cvd_context saved doctor={doctor_id} patient_id={patient_id} record_id={record_id} source={source!r} subtype={ctx.diagnosis_subtype!r}")
    return row


async def upsert_cvd_field(
    session: AsyncSession,
    record_id: int,
    patient_id: Optional[int],
    doctor_id: str,
    field_name: str,
    value: int,
) -> None:
    """Set a single field on an existing neuro_cvd_context row, or create a minimal row."""
    result = await session.execute(
        select(NeuroCVDContext)
        .where(NeuroCVDContext.record_id == record_id)
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing:
        data = json.loads(existing.raw_json or "{}")
        data[field_name] = value
        existing.raw_json = json.dumps(data, ensure_ascii=False)
        existing.updated_at = datetime.now(timezone.utc)
        # Keep promoted columns in sync
        if field_name == "diagnosis_subtype":
            existing.diagnosis_subtype = value
        elif field_name == "surgery_status":
            existing.surgery_status = value
    else:
        data = {field_name: value}
        row = NeuroCVDContext(
            record_id=record_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            source="manual",
            raw_json=json.dumps(data, ensure_ascii=False),
        )
        session.add(row)
    await session.commit()
    log(f"[silent-save] cvd_field upserted doctor={doctor_id} record_id={record_id} patient_id={patient_id} field={field_name!r} value={value}")


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
