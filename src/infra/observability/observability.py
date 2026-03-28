"""
请求链路追踪和 span 记录，将性能数据异步写入 JSONL 文件。

Public API and re-exports. Storage internals live in _storage.py;
query/aggregation functions live in _query.py.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import datetime, timezone
import time
import uuid
from typing import Any, Dict, List, Optional

from infra.observability._storage import (
    _LOCK,
    _PERSIST_SPANS_FILE,
    _PERSIST_TRACES_FILE,
    _SPAN_BUFFER,
    _TRACE_BUFFER,
    _disk_writer,           # re-exported for main.py startup
    _ensure_loaded,
    _enqueue_jsonl,
    _persist_enabled,
    _record_iso,
    SpanRecord,
    TraceRecord,
)
from infra.observability._query import (
    get_latency_summary,
    get_latency_summary_scoped,
    get_recent_spans,
    get_recent_spans_scoped,
    get_recent_traces,
    get_recent_traces_scoped,
    get_slowest_spans,
    get_slowest_spans_scoped,
    get_trace_timeline,
)

# Re-export disk writer so callers can do:
#   from infra.observability.observability import _disk_writer
__all__ = [
    # context management
    "trace_block",
    "set_current_trace_id",
    "reset_current_trace_id",
    "get_current_trace_id",
    "set_current_span_id",
    "reset_current_span_id",
    "get_current_span_id",
    # write
    "add_trace",
    "add_span",
    "clear_traces",
    # query (re-exported from _query)
    "get_recent_traces",
    "get_recent_traces_scoped",
    "get_recent_spans",
    "get_recent_spans_scoped",
    "get_trace_timeline",
    "get_slowest_spans",
    "get_slowest_spans_scoped",
    "get_latency_summary",
    "get_latency_summary_scoped",
    # internal background worker (used by main.py startup)
    "_disk_writer",
]


# ---------------------------------------------------------------------------
# Context variables for trace / span propagation
# ---------------------------------------------------------------------------

_TRACE_ID_CTX: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_SPAN_ID_CTX: ContextVar[Optional[str]] = ContextVar("span_id", default=None)


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


# ---------------------------------------------------------------------------
# Write functions
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# trace_block context manager
# ---------------------------------------------------------------------------

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
