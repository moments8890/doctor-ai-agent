"""
待确认病历和待处理消息的数据库操作。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import delete, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import PendingRecord, PendingMessage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# PendingRecord helpers (AI Record Confirmation Gate)
# ---------------------------------------------------------------------------

async def create_pending_record(
    session: AsyncSession,
    record_id: str,
    doctor_id: str,
    draft_json: str,
    patient_id: Optional[int] = None,
    patient_name: Optional[str] = None,
    ttl_minutes: int = 10,
) -> PendingRecord:
    now = datetime.now(timezone.utc)
    row = PendingRecord(
        id=record_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        patient_name=patient_name,
        draft_json=draft_json,
        status="awaiting",
        created_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    session.add(row)
    await session.commit()
    return row


async def get_pending_record(
    session: AsyncSession,
    record_id: str,
    doctor_id: str,
) -> Optional[PendingRecord]:
    result = await session.execute(
        select(PendingRecord).where(
            PendingRecord.id == record_id,
            PendingRecord.doctor_id == doctor_id,
        )
    )
    return result.scalar_one_or_none()


async def confirm_pending_record(
    session: AsyncSession,
    record_id: str,
    doctor_id: str,
) -> None:
    await session.execute(
        sa_update(PendingRecord).where(
            PendingRecord.id == record_id,
            PendingRecord.doctor_id == doctor_id,
            PendingRecord.status == "awaiting",
        ).values(status="confirmed")
    )
    await session.commit()


async def abandon_pending_record(
    session: AsyncSession,
    record_id: str,
    doctor_id: str,
) -> None:
    await session.execute(
        sa_update(PendingRecord).where(
            PendingRecord.id == record_id,
            PendingRecord.doctor_id == doctor_id,
        ).values(status="abandoned")
    )
    await session.commit()


async def get_stale_pending_records(session: AsyncSession) -> list:
    """Return all 'awaiting' PendingRecord rows that have passed their expires_at."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(PendingRecord).where(
            PendingRecord.status == "awaiting",
            PendingRecord.expires_at < now,
        )
    )
    return list(result.scalars().all())


async def expire_stale_pending_records(session: AsyncSession) -> int:
    """Mark 'awaiting' records past their expires_at as 'expired'. Returns count."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        sa_update(PendingRecord)
        .where(PendingRecord.status == "awaiting", PendingRecord.expires_at < now)
        .values(status="expired")
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0


async def purge_old_pending_records(session: AsyncSession, days: int = 30) -> int:
    """Hard-delete expired/abandoned/confirmed pending records older than `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        delete(PendingRecord).where(
            PendingRecord.status.in_(["expired", "abandoned", "confirmed"]),
            PendingRecord.expires_at < cutoff,
        )
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0


async def purge_old_pending_messages(session: AsyncSession, days: int = 30) -> int:
    """Hard-delete done PendingMessage rows older than `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        delete(PendingMessage).where(
            PendingMessage.status == "done",
            PendingMessage.created_at < cutoff,
        )
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0


# ---------------------------------------------------------------------------
# PendingMessage helpers
# ---------------------------------------------------------------------------

async def create_pending_message(
    session: AsyncSession,
    msg_id: str,
    doctor_id: str,
    raw_content: str,
) -> PendingMessage:
    row = PendingMessage(
        id=msg_id,
        doctor_id=doctor_id,
        raw_content=raw_content,
        status="pending",
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.commit()
    return row


async def mark_pending_message(
    session: AsyncSession,
    msg_id: str,
    status: str,
) -> None:
    await session.execute(
        sa_update(PendingMessage)
        .where(PendingMessage.id == msg_id)
        .values(status=status)
    )
    await session.commit()


async def increment_pending_message_attempt(
    session: AsyncSession,
    msg_id: str,
) -> None:
    """Increment attempt_count for a PendingMessage row."""
    await session.execute(
        sa_update(PendingMessage)
        .where(PendingMessage.id == msg_id)
        .values(attempt_count=PendingMessage.attempt_count + 1)
    )
    await session.commit()


async def list_stale_pending_messages(
    session: AsyncSession,
    older_than_seconds: int = 60,
) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
    result = await session.execute(
        select(PendingMessage)
        .where(PendingMessage.status == "pending", PendingMessage.created_at < cutoff)
        .order_by(PendingMessage.created_at)
        .limit(500)
    )
    return list(result.scalars().all())
