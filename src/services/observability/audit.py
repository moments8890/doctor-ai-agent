"""
敏感操作审计日志持久化，记录患者数据的增删改查行为。

Writes are buffered through an asyncio.Queue and flushed in batches by a
background worker (_audit_drain_worker) started from main.py lifespan.
This avoids one DB round-trip per audit event on the hot request path.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("audit")

# ---------------------------------------------------------------------------
# Internal queue — populated by audit(), drained by _audit_drain_worker()
# ---------------------------------------------------------------------------
_AUDIT_QUEUE: "asyncio.Queue[_AuditEntry] | None" = None
_QUEUE_MAXSIZE = 2000
_DRAIN_BATCH = 100
_DRAIN_INTERVAL = 5.0  # seconds


@dataclass
class _AuditEntry:
    doctor_id: str
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    ip: Optional[str]
    trace_id: Optional[str]
    ok: bool
    ts: datetime
    doctor_display_name: Optional[str]
    _retries: int = 0  # drain-worker retry counter (not persisted)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def audit(
    doctor_id: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip: Optional[str] = None,
    trace_id: Optional[str] = None,
    ok: bool = True,
    doctor_display_name: Optional[str] = None,
) -> None:
    """Enqueue an audit log entry.

    Non-blocking: the entry is placed on an in-memory queue and written to the
    DB in batches by the drain worker.  If the queue is full (very unlikely),
    falls back to a direct DB write so no audit events are silently dropped.

    The optional *doctor_display_name* parameter is persisted when the caller
    knows the doctor's human-readable name; otherwise it is left NULL.
    """
    entry = _AuditEntry(
        doctor_id=doctor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip=ip,
        trace_id=trace_id,
        ok=ok,
        ts=datetime.now(timezone.utc),
        doctor_display_name=doctor_display_name,
    )

    if _AUDIT_QUEUE is not None:
        try:
            _AUDIT_QUEUE.put_nowait(entry)
            return
        except asyncio.QueueFull:
            log.warning("[Audit] queue full — writing directly")

    # Fallback: synchronous-style direct write (startup / queue not started)
    await _write_entries([entry])


async def _write_entries(entries: list[_AuditEntry]) -> bool:
    """Persist a batch of audit entries in a single DB session.

    Returns True on success, False on failure (so the caller can re-queue).
    """
    if not entries:
        return True
    try:
        from db.engine import AsyncSessionLocal
        from db.models import AuditLog

        async with AsyncSessionLocal() as session:
            for e in entries:
                row = AuditLog(
                    doctor_id=e.doctor_id,
                    action=e.action,
                    resource_type=e.resource_type,
                    resource_id=e.resource_id,
                    ip=e.ip,
                    trace_id=e.trace_id,
                    ok=e.ok,
                )
                # Populate doctor_display_name if the column exists (added by
                # the models agent; older schemas tolerate the absence silently)
                if e.doctor_display_name is not None:
                    try:
                        row.doctor_display_name = e.doctor_display_name
                    except AttributeError:
                        pass
                session.add(row)
            await session.commit()
        return True
    except Exception as exc:
        log.warning("[Audit] batch write failed (%d entries): %s", len(entries), exc)
        return False


_MAX_RETRIES = 3  # per-entry retry cap before dropping


async def _audit_drain_worker() -> None:
    """Background task: drain _AUDIT_QUEUE in batches every _DRAIN_INTERVAL seconds.

    Start this once from main.py lifespan, analogous to _disk_writer() in
    services/observability/observability.py.

    On transient DB failure the batch is re-queued (up to _MAX_RETRIES per
    entry) so a short outage doesn't permanently lose audit events.
    """
    global _AUDIT_QUEUE
    _AUDIT_QUEUE = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    log.info("[Audit] drain worker started (batch=%d interval=%.0fs)", _DRAIN_BATCH, _DRAIN_INTERVAL)
    while True:
        try:
            await asyncio.sleep(_DRAIN_INTERVAL)
            batch: list[_AuditEntry] = []
            # Drain up to _DRAIN_BATCH items without blocking
            while len(batch) < _DRAIN_BATCH:
                try:
                    batch.append(_AUDIT_QUEUE.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if batch:
                ok = await _write_entries(batch)
                if ok:
                    for _ in batch:
                        try:
                            _AUDIT_QUEUE.task_done()
                        except ValueError:
                            pass
                else:
                    # Re-queue entries that haven't exhausted their retries.
                    requeued = 0
                    for entry in batch:
                        retries = entry._retries
                        if retries < _MAX_RETRIES:
                            entry._retries = retries + 1
                            try:
                                _AUDIT_QUEUE.put_nowait(entry)
                                requeued += 1
                            except asyncio.QueueFull:
                                pass
                        try:
                            _AUDIT_QUEUE.task_done()
                        except ValueError:
                            pass
                    dropped = len(batch) - requeued
                    if dropped:
                        log.warning(
                            "[Audit] dropped %d entries after %d retries",
                            dropped, _MAX_RETRIES,
                        )
        except asyncio.CancelledError:
            # Flush remaining entries before exit
            remaining: list[_AuditEntry] = []
            while True:
                try:
                    remaining.append(_AUDIT_QUEUE.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if remaining:
                await _write_entries(remaining)
            return
        except Exception as exc:
            log.warning("[Audit] drain worker error: %s", exc)
