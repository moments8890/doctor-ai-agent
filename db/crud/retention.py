"""
数据保留策略：定期清理过期的审计日志、病历版本历史等。
Retention policy CRUD: periodic deletion of old audit logs, record versions, and
chat archive entries so the DB does not grow unboundedly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog, ChatArchive, MedicalRecordVersion


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# AuditLog retention
# ---------------------------------------------------------------------------

async def archive_old_audit_logs(session: AsyncSession, days: int = 365) -> int:
    """Delete audit log entries older than *days* days.

    In production, export to cold storage before calling this.
    Returns the number of rows deleted.
    """
    cutoff = _utcnow() - timedelta(days=days)
    result = await session.execute(
        delete(AuditLog).where(AuditLog.ts < cutoff)
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0


# ---------------------------------------------------------------------------
# MedicalRecordVersion retention
# ---------------------------------------------------------------------------

async def prune_record_versions(session: AsyncSession, max_age_days: int = 730) -> int:
    """Delete medical record version entries older than *max_age_days* days.

    Keeps recent history intact; removes entries older than 2 years (default).
    A more sophisticated per-record "keep last N" strategy can be layered on
    top later via keyset pagination when needed.

    Returns the number of rows deleted.
    """
    cutoff = _utcnow() - timedelta(days=max_age_days)
    result = await session.execute(
        delete(MedicalRecordVersion).where(MedicalRecordVersion.changed_at < cutoff)
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0


# ---------------------------------------------------------------------------
# ChatArchive TTL retention
# ---------------------------------------------------------------------------

async def cleanup_chat_archive(session: AsyncSession, days: int = 90) -> int:
    """Hard-delete ChatArchive rows older than *days* days.

    Returns the number of rows deleted.
    """
    cutoff = _utcnow() - timedelta(days=days)
    result = await session.execute(
        delete(ChatArchive).where(ChatArchive.created_at < cutoff)
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0
