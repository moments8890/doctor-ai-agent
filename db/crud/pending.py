"""
待确认病历、批量导入和待处理消息的数据库操作。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import PendingRecord, PendingImport, PendingMessage


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
    raw_input: Optional[str] = None,
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
        raw_input=raw_input,
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


async def confirm_pending_record(session: AsyncSession, record_id: str) -> None:
    await session.execute(
        sa_update(PendingRecord)
        .where(PendingRecord.id == record_id)
        .values(status="confirmed")
    )
    await session.commit()


async def abandon_pending_record(session: AsyncSession, record_id: str) -> None:
    await session.execute(
        sa_update(PendingRecord)
        .where(PendingRecord.id == record_id)
        .values(status="abandoned")
    )
    await session.commit()


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


# ---------------------------------------------------------------------------
# PendingImport helpers (Bulk History Import Gate)
# ---------------------------------------------------------------------------

async def create_pending_import(
    session: AsyncSession,
    import_id: str,
    doctor_id: str,
    *,
    patient_id: Optional[int],
    patient_name: Optional[str],
    source: str,
    chunks_json: str,
    ttl_minutes: int = 30,
) -> PendingImport:
    expires = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    obj = PendingImport(
        id=import_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        patient_name=patient_name,
        source=source,
        chunks_json=chunks_json,
        status="awaiting",
        expires_at=expires,
    )
    session.add(obj)
    await session.commit()
    return obj


async def get_pending_import(
    session: AsyncSession,
    import_id: str,
    doctor_id: str,
) -> Optional[PendingImport]:
    result = await session.execute(
        select(PendingImport).where(
            PendingImport.id == import_id,
            PendingImport.doctor_id == doctor_id,
        )
    )
    return result.scalar_one_or_none()


async def confirm_pending_import(session: AsyncSession, import_id: str) -> None:
    await session.execute(
        sa_update(PendingImport)
        .where(PendingImport.id == import_id)
        .values(status="confirmed")
    )
    await session.commit()


async def abandon_pending_import(session: AsyncSession, import_id: str) -> None:
    await session.execute(
        sa_update(PendingImport)
        .where(PendingImport.id == import_id)
        .values(status="abandoned")
    )
    await session.commit()


async def expire_stale_pending_imports(session: AsyncSession) -> int:
    result = await session.execute(
        sa_update(PendingImport)
        .where(
            PendingImport.status == "awaiting",
            PendingImport.expires_at < datetime.now(timezone.utc),
        )
        .values(status="expired")
    )
    await session.commit()
    return result.rowcount


# ---------------------------------------------------------------------------
# PendingMessage helpers
# ---------------------------------------------------------------------------

async def create_pending_message(
    session: AsyncSession,
    msg_id: str,
    doctor_id: str,
    raw_content: str,
    msg_type: str = "text",
) -> PendingMessage:
    row = PendingMessage(
        id=msg_id,
        doctor_id=doctor_id,
        raw_content=raw_content,
        msg_type=msg_type,
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
    error: Optional[str] = None,
) -> None:
    await session.execute(
        sa_update(PendingMessage)
        .where(PendingMessage.id == msg_id)
        .values(status=status, error=error, processed_at=datetime.now(timezone.utc))
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
    )
    return list(result.scalars().all())
