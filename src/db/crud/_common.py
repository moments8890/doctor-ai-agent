"""
db.crud 子模块的共享辅助工具。
Shared helpers used across db.crud sub-modules.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _trace_block(layer: str, name: str, meta: dict | None = None):
    """Lazy-import trace_block to avoid db/ -> services/ module-level dependency."""
    from infra.observability.observability import trace_block
    return trace_block(layer, name, meta)
