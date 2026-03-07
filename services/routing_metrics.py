"""
Lightweight in-process counters for fast-router vs LLM routing decisions.

Counters are keyed by the routing label produced by fast_route_label():
  "fast:list_patients", "fast:query_records", ..., "llm"

Thread-safe. Zero external dependencies. Resets on process restart.
"""
from __future__ import annotations

from threading import Lock
from typing import Dict

_lock = Lock()
_counters: Dict[str, int] = {}


def record(label: str) -> None:
    """Increment counter for a routing label."""
    with _lock:
        _counters[label] = _counters.get(label, 0) + 1


def get_metrics() -> Dict:
    """Return a snapshot of routing counters and derived rates."""
    with _lock:
        snapshot = dict(_counters)
    total = sum(snapshot.values())
    fast_total = sum(v for k, v in snapshot.items() if k.startswith("fast:"))
    llm_total = snapshot.get("llm", 0)
    hit_rate = round(fast_total / total * 100, 1) if total else 0.0
    return {
        "total_routed": total,
        "fast_hits": fast_total,
        "llm_hits": llm_total,
        "fast_hit_rate_pct": hit_rate,
        "by_intent": dict(sorted(snapshot.items())),
    }


def reset() -> None:
    """Reset all counters (useful in tests or after a deployment)."""
    with _lock:
        _counters.clear()
