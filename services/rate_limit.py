from __future__ import annotations

import os
import time
from collections import deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException

_RATE_WINDOWS: Dict[Tuple[str, str], Deque[float]] = {}


def _max_requests_per_minute() -> int:
    raw = os.environ.get("API_RATE_LIMIT_PER_MIN", "100")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 100


def enforce_doctor_rate_limit(
    doctor_id: str,
    *,
    scope: str,
    max_requests: int | None = None,
    window_seconds: float = 60.0,
) -> None:
    limit = max_requests if max_requests is not None else _max_requests_per_minute()
    now = time.time()
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
    _RATE_WINDOWS.clear()
