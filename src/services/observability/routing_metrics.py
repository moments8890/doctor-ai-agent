"""
路由决策计数器：统计快速路由与 LLM 路由的命中率，线程安全，进程重启后清零。
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
