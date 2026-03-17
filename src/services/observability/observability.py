"""
请求链路追踪和 span 记录，将性能数据异步写入 JSONL 文件。
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from threading import Lock
import time
import uuid
import logging
from typing import Any, Deque, Dict, List, Optional

_obs_log = logging.getLogger("observability")


@dataclass
class TraceRecord:
    trace_id: str
    started_at: datetime
    method: str
    path: str
    status_code: int
    latency_ms: float


@dataclass
class SpanRecord:
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    layer: str
    name: str
    started_at: datetime
    latency_ms: float
    status: str
    meta: Dict[str, Any]


_MAX_TRACES = 2000
_TRACE_BUFFER: Deque[TraceRecord] = deque(maxlen=_MAX_TRACES)
_MAX_SPANS = 10000
_SPAN_BUFFER: Deque[SpanRecord] = deque(maxlen=_MAX_SPANS)
_LOCK = Lock()
_TRACE_ID_CTX: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_SPAN_ID_CTX: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
_INTERNAL_PATH_PREFIXES = ("/api/admin", "/api/manage")
_PERSIST_DIR = Path(os.environ.get("OBSERVABILITY_DIR", "logs"))
_PERSIST_TRACES_FILE = _PERSIST_DIR / "observability_traces.jsonl"
_PERSIST_SPANS_FILE = _PERSIST_DIR / "observability_spans.jsonl"
_TTL_DAYS = int(os.environ.get("OBSERVABILITY_TTL_DAYS", "7"))
_PRUNE_EVERY = 200
_LOADED = False
_SPAN_WRITE_QUEUE: "asyncio.Queue[tuple[Path, dict]] | None" = None


def _persist_enabled() -> bool:
    if os.environ.get("OBSERVABILITY_PERSIST", "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    # Keep unit tests side-effect free.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return True


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _cutoff() -> datetime:
    return _utc_now() - timedelta(days=_TTL_DAYS)


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    if not _persist_enabled():
        return
    _load_from_disk()


def _record_iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _enqueue_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    """Non-blocking enqueue for async disk writer. Falls back to sync write if writer not started."""
    if _SPAN_WRITE_QUEUE is not None:
        try:
            _SPAN_WRITE_QUEUE.put_nowait((path, payload))
            return
        except asyncio.QueueFull:
            pass
    # Fallback: sync write (startup phase or tests)
    _append_jsonl(path, payload)


async def _disk_writer() -> None:
    """Background coroutine: drains the write queue to disk without blocking the event loop."""
    global _SPAN_WRITE_QUEUE
    _SPAN_WRITE_QUEUE = asyncio.Queue(maxsize=5000)
    _items_written = 0
    while True:
        try:
            path, payload = await _SPAN_WRITE_QUEUE.get()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                _items_written += 1
                if _items_written % _PRUNE_EVERY == 0:
                    await asyncio.get_event_loop().run_in_executor(None, _prune_disk_files)
            except Exception:
                _obs_log.warning("span disk write failed", exc_info=True)
            finally:
                _SPAN_WRITE_QUEUE.task_done()
        except Exception:
            _obs_log.warning("span queue drain failed", exc_info=True)


def _load_from_disk() -> None:
    cutoff = _cutoff()
    if _PERSIST_TRACES_FILE.exists():
        try:
            for line in _PERSIST_TRACES_FILE.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                started_at = _parse_iso(str(row.get("started_at", "")))
                if not started_at or started_at < cutoff:
                    continue
                _TRACE_BUFFER.append(
                    TraceRecord(
                        trace_id=str(row.get("trace_id", "")),
                        started_at=started_at,
                        method=str(row.get("method", "")),
                        path=str(row.get("path", "")),
                        status_code=int(row.get("status_code", 0)),
                        latency_ms=float(row.get("latency_ms", 0.0)),
                    )
                )
        except Exception:
            _obs_log.warning("load traces from disk failed", exc_info=True)
    if _PERSIST_SPANS_FILE.exists():
        try:
            for line in _PERSIST_SPANS_FILE.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                started_at = _parse_iso(str(row.get("started_at", "")))
                if not started_at or started_at < cutoff:
                    continue
                _SPAN_BUFFER.append(
                    SpanRecord(
                        trace_id=str(row.get("trace_id", "")),
                        span_id=str(row.get("span_id", "")),
                        parent_span_id=row.get("parent_span_id"),
                        layer=str(row.get("layer", "")),
                        name=str(row.get("name", "")),
                        started_at=started_at,
                        latency_ms=float(row.get("latency_ms", 0.0)),
                        status=str(row.get("status", "ok")),
                        meta=dict(row.get("meta") or {}),
                    )
                )
        except Exception:
            _obs_log.warning("load spans from disk failed", exc_info=True)
    _prune_disk_files()


def _prune_disk_files() -> None:
    if not _persist_enabled():
        return
    cutoff = _cutoff()

    def _prune(path: Path) -> None:
        if not path.exists():
            return
        kept: List[str] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                started_at = _parse_iso(str(row.get("started_at", "")))
                if started_at and started_at >= cutoff:
                    kept.append(json.dumps(row, ensure_ascii=False))
            path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
        except Exception:
            _obs_log.warning("prune disk file failed: %s", path, exc_info=True)

    _prune(_PERSIST_TRACES_FILE)
    _prune(_PERSIST_SPANS_FILE)


def add_trace(
    trace_id: str,
    started_at: datetime,
    method: str,
    path: str,
    status_code: int,
    latency_ms: float,
) -> None:
    _ensure_loaded()
    with _LOCK:
        _TRACE_BUFFER.append(
            TraceRecord(
                trace_id=trace_id,
                started_at=started_at,
                method=method,
                path=path,
                status_code=status_code,
                latency_ms=latency_ms,
            )
        )
    if _persist_enabled():
        _enqueue_jsonl(
            _PERSIST_TRACES_FILE,
            {
                "trace_id": trace_id,
                "started_at": _record_iso(started_at),
                "method": method,
                "path": path,
                "status_code": status_code,
                "latency_ms": latency_ms,
            },
        )


def set_current_trace_id(trace_id: str) -> Token:
    return _TRACE_ID_CTX.set(trace_id)


def reset_current_trace_id(token: Token) -> None:
    _TRACE_ID_CTX.reset(token)


def get_current_trace_id() -> Optional[str]:
    return _TRACE_ID_CTX.get()


def set_current_span_id(span_id: Optional[str]) -> Token:
    return _SPAN_ID_CTX.set(span_id)


def reset_current_span_id(token: Token) -> None:
    _SPAN_ID_CTX.reset(token)


def get_current_span_id() -> Optional[str]:
    return _SPAN_ID_CTX.get()


def add_span(
    trace_id: str,
    layer: str,
    name: str,
    started_at: datetime,
    latency_ms: float,
    status: str = "ok",
    meta: Optional[Dict[str, Any]] = None,
    span_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
) -> None:
    _ensure_loaded()
    # Redact PHI from span metadata before persisting/buffering.
    clean_meta = dict(meta or {})
    if "patient_name" in clean_meta:
        import hashlib
        _pn = str(clean_meta.pop("patient_name"))
        clean_meta["patient_name_hash"] = hashlib.sha256(_pn.encode()).hexdigest()[:12]
    # patient_id is an internal integer — retain for correlation but not PHI.
    rec = SpanRecord(
        trace_id=trace_id,
        span_id=span_id or uuid.uuid4().hex[:12],
        parent_span_id=parent_span_id,
        layer=layer,
        name=name,
        started_at=started_at,
        latency_ms=latency_ms,
        status=status,
        meta=clean_meta,
    )
    with _LOCK:
        _SPAN_BUFFER.append(rec)
    if _persist_enabled():
        _enqueue_jsonl(
            _PERSIST_SPANS_FILE,
            {
                "trace_id": rec.trace_id,
                "span_id": rec.span_id,
                "parent_span_id": rec.parent_span_id,
                "layer": rec.layer,
                "name": rec.name,
                "started_at": _record_iso(rec.started_at),
                "latency_ms": rec.latency_ms,
                "status": rec.status,
                "meta": rec.meta,
            },
        )


@contextmanager
def trace_block(layer: str, name: str, meta: Optional[Dict[str, Any]] = None):
    trace_id = get_current_trace_id()
    if not trace_id:
        yield
        return

    started_at = datetime.now(timezone.utc)
    start_clock = time.perf_counter()
    span_id = uuid.uuid4().hex[:12]
    parent_span_id = get_current_span_id()
    span_token = set_current_span_id(span_id)

    try:
        yield
    except Exception:
        add_span(
            trace_id=trace_id,
            layer=layer,
            name=name,
            started_at=started_at,
            latency_ms=(time.perf_counter() - start_clock) * 1000.0,
            status="error",
            meta=meta,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
        raise
    else:
        add_span(
            trace_id=trace_id,
            layer=layer,
            name=name,
            started_at=started_at,
            latency_ms=(time.perf_counter() - start_clock) * 1000.0,
            status="ok",
            meta=meta,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )
    finally:
        reset_current_span_id(span_token)


def get_recent_traces(limit: int = 100) -> List[Dict]:
    return get_recent_traces_scoped(limit=limit, scope="all")


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


def clear_traces() -> None:
    with _LOCK:
        _TRACE_BUFFER.clear()
        _SPAN_BUFFER.clear()
    if _persist_enabled():
        try:
            _PERSIST_TRACES_FILE.unlink(missing_ok=True)
            _PERSIST_SPANS_FILE.unlink(missing_ok=True)
        except Exception:
            pass
