"""In-memory message de-duplication with TTL (ADR 0011 §5)."""
from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional, Set

from services.runtime.models import TurnResult

_TTL_SECONDS = 300  # 5 minutes
_cache: Dict[str, tuple[float, TurnResult]] = {}
# Tracks message_ids currently being processed to prevent concurrent duplicates.
_in_flight: Set[str] = set()
_lock = asyncio.Lock()


async def try_acquire(message_id: str) -> Optional[TurnResult]:
    """Atomically check dedup cache and mark message as in-flight.

    Returns the cached TurnResult if this is a duplicate, or None if the
    caller should proceed with processing.  The caller MUST call
    ``cache_result()`` after processing to release the in-flight slot.
    """
    async with _lock:
        entry = _cache.get(message_id)
        if entry is not None:
            ts, result = entry
            if time.monotonic() - ts <= _TTL_SECONDS:
                return result
            _cache.pop(message_id, None)
        if message_id in _in_flight:
            # Another coroutine is already processing this message.
            # Return a sentinel so the caller can drop the duplicate.
            return TurnResult(reply="")
        _in_flight.add(message_id)
    return None


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
    """Cache a TurnResult for de-duplication and release in-flight slot."""
    _cache[message_id] = (time.monotonic(), result)
    _in_flight.discard(message_id)
    _evict_stale()


def _evict_stale() -> None:
    if len(_cache) < 500:
        return
    now = time.monotonic()
    for k in [k for k, (ts, _) in _cache.items() if now - ts > _TTL_SECONDS]:
        _cache.pop(k, None)
