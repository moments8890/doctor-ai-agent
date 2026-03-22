"""
患者门户消息的 CRUD 操作：保存和查询消息。
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.patient_message import PatientMessage


async def save_patient_message(
    session: AsyncSession,
    patient_id: int,
    doctor_id: str,
    content: str,
    direction: str = "inbound",
    source: Optional[str] = None,
) -> PatientMessage:
    """Persist a patient portal message and return the created row.

    If *source* is not explicitly supplied, it is inferred from *direction*:
    ``inbound`` → ``patient``, ``outbound`` → ``ai``.
    """
    if source is None:
        source = "patient" if direction == "inbound" else "ai"
    msg = PatientMessage(
        patient_id=patient_id,
        doctor_id=doctor_id,
        content=content,
        direction=direction,
        source=source,
    )
    session.add(msg)
    await session.commit()
    return msg


async def list_patient_messages(
    session: AsyncSession,
    patient_id: int,
    doctor_id: str,
    limit: int = 50,
) -> List[PatientMessage]:
    """Return recent messages for a patient, newest first.

    Enforces doctor_id ownership to prevent cross-doctor data access.
    """
    result = await session.execute(
        select(PatientMessage)
        .where(
            PatientMessage.patient_id == patient_id,
            PatientMessage.doctor_id == doctor_id,
        )
        .order_by(PatientMessage.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
