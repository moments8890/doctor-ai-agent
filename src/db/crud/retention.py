"""
数据保留策略：定期清理过期的审计日志、病历版本历史等。
Retention policy CRUD: periodic deletion of old audit logs, record versions, and
chat archive entries so the DB does not grow unboundedly.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog, ChatArchive, MedicalRecordVersion
from db.crud._common import _utcnow


# ---------------------------------------------------------------------------
# AuditLog retention
# ---------------------------------------------------------------------------

async def archive_old_audit_logs(session: AsyncSession, days: int = 2555) -> int:
    """Delete audit log entries older than *days* days (default 7 years / 2555 days).

    Chinese MoH best practice: retain audit logs 7+ years for regulatory compliance.
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

async def prune_record_versions(session: AsyncSession, max_age_days: int = 10950) -> int:
    """Delete medical record version entries older than *max_age_days* days (default 30 years).

    Chinese MoH regulation (医疗机构病历管理规定 2013): inpatient records must be
    retained for 30 years after discharge. Record version history should match.

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

async def cleanup_chat_archive(session: AsyncSession, days: int = 365) -> int:
    """Hard-delete ChatArchive rows older than *days* days (default 1 year).

    Chat archives contain clinical context used for model evaluation. 365 days
    balances storage cost against the need to reconstruct care timelines.
    Returns the number of rows deleted.
    """
    cutoff = _utcnow() - timedelta(days=days)
    result = await session.execute(
        delete(ChatArchive).where(ChatArchive.created_at < cutoff)
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0


