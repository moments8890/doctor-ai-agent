"""In-memory message de-duplication with TTL (ADR 0011 §5)."""
from __future__ import annotations

import time
from typing import Dict, Optional

from services.runtime.models import TurnResult

_TTL_SECONDS = 300  # 5 minutes
_cache: Dict[str, tuple[float, TurnResult]] = {}


def is_duplicate(message_id: str) -> bool:
    """Return True if this message_id was already processed within TTL."""
    entry = _cache.get(message_id)
    if entry is None:
        return False
    ts, _ = entry
    if time.monotonic() - ts > _TTL_SECONDS:
        _cache.pop(message_id, None)
        return False
    return True


def get_cached_result(message_id: str) -> Optional[TurnResult]:
    """Return the cached TurnResult for a duplicate message_id."""
    entry = _cache.get(message_id)
    return entry[1] if entry else None


def cache_result(message_id: str, result: TurnResult) -> None:
    """Cache a TurnResult for de-duplication."""
    _cache[message_id] = (time.monotonic(), result)
    _evict_stale()


def _evict_stale() -> None:
    if len(_cache) < 500:
        return
    now = time.monotonic()
    for k in [k for k, (ts, _) in _cache.items() if now - ts > _TTL_SECONDS]:
        _cache.pop(k, None)
