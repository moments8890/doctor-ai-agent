"""
Query and retrieval functions for recent traces, spans, timelines, and latency summaries.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Optional

from infra.observability._storage import (
    _INTERNAL_PATH_PREFIXES,
    _LOCK,
    _SPAN_BUFFER,
    _TRACE_BUFFER,
    _ensure_loaded,
    TraceRecord,
)


# ---------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------


def _trace_scope(path: str) -> str:
    for prefix in _INTERNAL_PATH_PREFIXES:
        if path.startswith(prefix):
            return "internal"
    return "public"


def _scope_match(path: str, scope: str) -> bool:
    if scope == "all":
        return True
    return _trace_scope(path) == scope


def _trace_rows_scoped(scope: str = "all") -> List[TraceRecord]:
    with _LOCK:
        rows = list(_TRACE_BUFFER)
    if scope not in {"all", "public", "internal"}:
        scope = "all"
    if scope == "all":
        return rows
    return [row for row in rows if _scope_match(row.path, scope)]


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def get_recent_traces(limit: int = 100) -> List[Dict]:
    return get_recent_traces_scoped(limit=limit, scope="all")


def get_recent_traces_scoped(limit: int = 100, scope: str = "all") -> List[Dict]:
    _ensure_loaded()
    safe_limit = max(1, min(limit, 1000))
    rows = _trace_rows_scoped(scope=scope)[-safe_limit:]
    rows.reverse()
    return [asdict(row) for row in rows]


def get_recent_spans(limit: int = 200, trace_id: Optional[str] = None) -> List[Dict]:
    return get_recent_spans_scoped(limit=limit, trace_id=trace_id, scope="all")


def get_recent_spans_scoped(limit: int = 200, trace_id: Optional[str] = None, scope: str = "all") -> List[Dict]:
    _ensure_loaded()
    safe_limit = max(1, min(limit, 2000))
    allowed_trace_ids: Optional[set] = None
    if scope in {"public", "internal"}:
        allowed_trace_ids = {row.trace_id for row in _trace_rows_scoped(scope=scope)}
    with _LOCK:
        rows = list(_SPAN_BUFFER)
    if trace_id:
        rows = [row for row in rows if row.trace_id == trace_id]
    if allowed_trace_ids is not None:
        rows = [row for row in rows if row.trace_id in allowed_trace_ids]
    rows = rows[-safe_limit:]
    rows.reverse()
    return [asdict(row) for row in rows]


def get_trace_timeline(trace_id: str, limit: int = 500) -> List[Dict]:
    _ensure_loaded()
    safe_limit = max(1, min(limit, 2000))
    with _LOCK:
        rows = [row for row in _SPAN_BUFFER if row.trace_id == trace_id]
    rows.sort(key=lambda row: row.started_at)
    rows = rows[:safe_limit]
    return [asdict(row) for row in rows]


def get_slowest_spans(limit: int = 30) -> List[Dict]:
    return get_slowest_spans_scoped(limit=limit, scope="all")


def get_slowest_spans_scoped(limit: int = 30, scope: str = "all") -> List[Dict]:
    _ensure_loaded()
    safe_limit = max(1, min(limit, 200))
    allowed_trace_ids: Optional[set] = None
    if scope in {"public", "internal"}:
        allowed_trace_ids = {row.trace_id for row in _trace_rows_scoped(scope=scope)}
    with _LOCK:
        rows = list(_SPAN_BUFFER)
    if allowed_trace_ids is not None:
        rows = [row for row in rows if row.trace_id in allowed_trace_ids]
    rows.sort(key=lambda row: row.latency_ms, reverse=True)
    return [asdict(row) for row in rows[:safe_limit]]


def _percentile(values: List[float], ratio: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    idx = int((len(sorted_values) - 1) * ratio)
    return sorted_values[idx]


def get_latency_summary(limit: int = 500) -> Dict:
    return get_latency_summary_scoped(limit=limit, scope="all")


def get_latency_summary_scoped(limit: int = 500, scope: str = "all") -> Dict:
    _ensure_loaded()
    safe_limit = max(1, min(limit, 2000))
    rows = _trace_rows_scoped(scope=scope)[-safe_limit:]

    latencies = [row.latency_ms for row in rows]
    per_path: Dict[str, Dict[str, float]] = {}
    status_counts: Dict[str, int] = {}

    for row in rows:
        path_stats = per_path.setdefault(row.path, {"count": 0, "avg_ms": 0.0, "max_ms": 0.0})
        path_stats["count"] += 1
        path_stats["avg_ms"] += row.latency_ms
        path_stats["max_ms"] = max(path_stats["max_ms"], row.latency_ms)
        code = str(row.status_code)
        status_counts[code] = status_counts.get(code, 0) + 1

    for stats in per_path.values():
        if stats["count"] > 0:
            stats["avg_ms"] = round(stats["avg_ms"] / stats["count"], 3)
        stats["max_ms"] = round(stats["max_ms"], 3)

    avg_ms = round(sum(latencies) / len(latencies), 3) if latencies else 0.0
    max_ms = round(max(latencies), 3) if latencies else 0.0

    return {
        "count": len(rows),
        "avg_ms": avg_ms,
        "max_ms": max_ms,
        "p50_ms": round(_percentile(latencies, 0.50), 3),
        "p95_ms": round(_percentile(latencies, 0.95), 3),
        "p99_ms": round(_percentile(latencies, 0.99), 3),
        "status_counts": status_counts,
        "per_path": per_path,
    }
