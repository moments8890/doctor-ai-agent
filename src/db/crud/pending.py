"""
待确认病历和待处理消息的数据库操作。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import delete, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import PendingRecord, PendingMessage
from db.models.pending import PendingRecordStatus, PendingMessageStatus


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
        status=PendingRecordStatus.awaiting,
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
    commit: bool = True,
) -> bool:
    """Mark an awaiting pending record as confirmed.

    Returns True if a row was updated, False if the record was not found,
    already processed, or expired (expires_at enforced at SQL level).
    """
    now = datetime.now(timezone.utc)
    result = await session.execute(
        sa_update(PendingRecord).where(
            PendingRecord.id == record_id,
            PendingRecord.doctor_id == doctor_id,
            PendingRecord.status == PendingRecordStatus.awaiting,
            PendingRecord.expires_at > now,
        ).values(status=PendingRecordStatus.confirmed)
    )
    if commit:
        await session.commit()
    return (result.rowcount or 0) > 0


async def force_confirm_pending_record(
    session: AsyncSession,
    record_id: str,
    doctor_id: str,
    commit: bool = True,
) -> bool:
    """Atomically mark an awaiting pending record as confirmed.

    Unlike ``confirm_pending_record``, this does NOT check ``expires_at``.
    Used by the stale-draft auto-save scheduler, which intentionally processes
    already-expired drafts so they don't get re-processed on the next tick.

    Returns True if the transition succeeded (row was still 'awaiting'),
    False if another process already claimed it.
    """
    result = await session.execute(
        sa_update(PendingRecord).where(
            PendingRecord.id == record_id,
            PendingRecord.doctor_id == doctor_id,
            PendingRecord.status == PendingRecordStatus.awaiting,
        ).values(status=PendingRecordStatus.confirmed)
    )
    if commit:
        await session.commit()
    return (result.rowcount or 0) > 0


async def abandon_pending_record(
    session: AsyncSession,
    record_id: str,
    doctor_id: str,
) -> None:
    await session.execute(
        sa_update(PendingRecord).where(
            PendingRecord.id == record_id,
            PendingRecord.doctor_id == doctor_id,
        ).values(status=PendingRecordStatus.abandoned)
    )
    await session.commit()


async def update_pending_draft(
    session: AsyncSession,
    record_id: str,
    doctor_id: str,
    new_draft_json: str,
    ttl_minutes: int = 10,
) -> None:
    """Update draft_json for an awaiting pending record and reset its expiry."""
    new_expires = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    await session.execute(
        sa_update(PendingRecord).where(
            PendingRecord.id == record_id,
            PendingRecord.doctor_id == doctor_id,
            PendingRecord.status == PendingRecordStatus.awaiting,
        ).values(draft_json=new_draft_json, expires_at=new_expires)
    )
    await session.commit()


async def get_stale_pending_records(session: AsyncSession) -> list:
    """Return all 'awaiting' PendingRecord rows that have passed their expires_at."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(PendingRecord).where(
            PendingRecord.status == PendingRecordStatus.awaiting,
            PendingRecord.expires_at < now,
        )
    )
    return list(result.scalars().all())


async def expire_stale_pending_records(session: AsyncSession) -> int:
    """Mark 'awaiting' records past their expires_at as 'expired'. Returns count."""
    now = datetime.now(timezone.utc)
    result = await session.execute(
        sa_update(PendingRecord)
        .where(PendingRecord.status == PendingRecordStatus.awaiting, PendingRecord.expires_at < now)
        .values(status=PendingRecordStatus.expired)
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0


async def purge_old_pending_records(session: AsyncSession, days: int = 30) -> int:
    """Hard-delete expired/abandoned/confirmed pending records older than `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        delete(PendingRecord).where(
            PendingRecord.status.in_([PendingRecordStatus.expired, PendingRecordStatus.abandoned, PendingRecordStatus.confirmed]),
            PendingRecord.expires_at < cutoff,
        )
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0


async def purge_old_pending_messages(session: AsyncSession, days: int = 30) -> int:
    """Hard-delete done and dead-letter PendingMessage rows older than `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        delete(PendingMessage).where(
            PendingMessage.status.in_([PendingMessageStatus.done, PendingMessageStatus.dead]),
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
        status=PendingMessageStatus.pending,
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.commit()
    return row


async def mark_pending_message(
    session: AsyncSession,
    msg_id: str,
    status: PendingMessageStatus,
) -> None:
    if not isinstance(status, PendingMessageStatus):
        raise ValueError(f"Invalid PendingMessage status: {status!r}")
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
    """Return stale messages eligible for recovery.

    First resets any long-stuck 'processing' rows back to 'pending' so
    they can be re-claimed via the normal pending → processing path.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
    # Reset stuck processing rows so claim_pending_message can re-acquire them.
    await session.execute(
        sa_update(PendingMessage)
        .where(PendingMessage.status == PendingMessageStatus.processing, PendingMessage.created_at < cutoff)
        .values(status=PendingMessageStatus.pending)
    )
    await session.commit()
    result = await session.execute(
        select(PendingMessage)
        .where(PendingMessage.status == PendingMessageStatus.pending, PendingMessage.created_at < cutoff)
        .order_by(PendingMessage.created_at)
        .limit(500)
    )
    return list(result.scalars().all())


async def claim_pending_message(
    session: AsyncSession,
    msg_id: str,
) -> bool:
    """Atomically claim a pending message for processing.

    Transitions status from 'pending' to 'processing' and increments
    attempt_count.  Returns True if the row was claimed (i.e. it was
    still in 'pending' status), False otherwise (already claimed by
    another instance or marked done/dead).

    Only accepts rows in 'pending' status — rows already in 'processing'
    are not re-claimed.  The recovery path should reset long-stuck
    processing rows back to 'pending' before re-claiming.
    """
    result = await session.execute(
        sa_update(PendingMessage)
        .where(PendingMessage.id == msg_id, PendingMessage.status == PendingMessageStatus.pending)
        .values(status=PendingMessageStatus.processing, attempt_count=PendingMessage.attempt_count + 1)
    )
    await session.commit()
    return result.rowcount > 0
