"""
数据保留策略：定期清理过期的审计日志等。
Retention policy CRUD: periodic deletion of old audit logs and
chat archive entries so the DB does not grow unboundedly.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog
from db.models.doctor_chat_log import DoctorChatLog
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
# DoctorChatLog TTL retention
# ---------------------------------------------------------------------------

async def cleanup_chat_log(session: AsyncSession, days: int = 365) -> int:
    """Hard-delete DoctorChatLog rows older than *days* days (default 1 year).

    Chat logs contain clinical context used for model evaluation. 365 days
    balances storage cost against the need to reconstruct care timelines.
    Returns the number of rows deleted.
    """
    cutoff = _utcnow() - timedelta(days=days)
    result = await session.execute(
        delete(DoctorChatLog).where(DoctorChatLog.created_at < cutoff)
    )
    await session.commit()
    return result.rowcount if result.rowcount else 0
