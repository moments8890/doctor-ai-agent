"""
基于滑动窗口的内存速率限制器，防止接口被单一用户高频调用。
"""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException

_RATE_WINDOWS: Dict[Tuple[str, str], Deque[float]] = {}

# Pruning: every _PRUNE_INTERVAL_S seconds, evict keys whose newest
# timestamp is older than the window.  This prevents unbounded growth
# from one-off callers that never return.
_PRUNE_INTERVAL_S: float = 300.0  # 5 minutes
_last_prune: float = 0.0


def _max_requests_per_minute() -> int:
    raw = os.environ.get("API_RATE_LIMIT_PER_MIN", "100")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 100


def _maybe_prune(now: float, max_window: float = 60.0) -> None:
    """Evict stale keys if enough time has passed since the last prune."""
    global _last_prune
    if now - _last_prune < _PRUNE_INTERVAL_S:
        return
    _last_prune = now
    cutoff = now - max_window
    stale = [k for k, q in _RATE_WINDOWS.items() if not q or q[-1] < cutoff]
    for k in stale:
        del _RATE_WINDOWS[k]


def enforce_doctor_rate_limit(
    doctor_id: str,
    *,
    scope: str,
    max_requests: int | None = None,
    window_seconds: float = 60.0,
) -> None:
    limit = max_requests if max_requests is not None else _max_requests_per_minute()
    now = time.time()
    _maybe_prune(now, max_window=window_seconds)
    window_start = now - window_seconds
    key = (scope, doctor_id)
    q = _RATE_WINDOWS.setdefault(key, deque())
    while q and q[0] < window_start:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(
            status_code=429,
            detail="rate_limit_exceeded",
            headers={"Retry-After": str(int(window_seconds))},
        )
    q.append(now)


def clear_rate_limits_for_tests() -> None:
    global _last_prune
    _RATE_WINDOWS.clear()
    _last_prune = 0.0


def _client_ip_from_request(request) -> str:
    """Best-effort client IP. Trusts X-Forwarded-For when set (nginx in front)."""
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        # Left-most entry is the original client.
        return xff.split(",", 1)[0].strip() or "unknown"
    real = (request.headers.get("X-Real-IP") or "").strip()
    if real:
        return real
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def enforce_ip_rate_limit(
    request,
    *,
    scope: str,
    max_requests: int,
    window_seconds: float = 60.0,
) -> None:
    """Per-IP sliding-window limiter for unauthenticated endpoints (login, etc.).

    Uses the same shared deque map as the doctor-keyed limiter, so both share
    the prune cycle. Scope must be distinct between use sites.
    """
    ip = _client_ip_from_request(request)
    now = time.time()
    _maybe_prune(now, max_window=window_seconds)
    window_start = now - window_seconds
    key = (scope, ip)
    q = _RATE_WINDOWS.setdefault(key, deque())
    while q and q[0] < window_start:
        q.popleft()
    if len(q) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail="rate_limit_exceeded",
            headers={"Retry-After": str(int(window_seconds))},
        )
    q.append(now)
