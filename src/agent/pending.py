"""Pending record helpers — query pending_records table directly.

No  dependency. Pending state lives in pending_records table.
"""
from __future__ import annotations

from typing import Optional

from db.engine import AsyncSessionLocal
from db.models.pending import PendingRecord
from sqlalchemy import select


async def get_pending_draft_id(doctor_id: str) -> Optional[str]:
    """Get the ID of the most recent awaiting pending record for this doctor."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PendingRecord.id)
            .where(
                PendingRecord.doctor_id == doctor_id,
                PendingRecord.status == "awaiting",
            )
            .order_by(PendingRecord.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


async def clear_pending_draft_id(doctor_id: str) -> None:
    """No-op — pending state lives in pending_records table.

    When a record is confirmed/abandoned, the pending_records row status
    is updated directly. No separate 'pointer' to clear.
    """
    pass
