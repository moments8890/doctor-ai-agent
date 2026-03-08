"""
敏感操作审计日志持久化，记录患者数据的增删改查行为。
"""

from __future__ import annotations

import logging
from typing import Optional

from db.engine import AsyncSessionLocal
from db.models import AuditLog

log = logging.getLogger("audit")


async def audit(
    doctor_id: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip: Optional[str] = None,
    trace_id: Optional[str] = None,
    ok: bool = True,
) -> None:
    """Write a single audit log entry.

    Swallows all exceptions so audit failures never break the request path.
    """
    try:
        async with AsyncSessionLocal() as session:
            session.add(AuditLog(
                doctor_id=doctor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip=ip,
                trace_id=trace_id,
                ok=ok,
            ))
            await session.commit()
    except Exception as exc:
        log.warning("[Audit] write failed doctor=%s action=%s: %s", doctor_id, action, exc)
