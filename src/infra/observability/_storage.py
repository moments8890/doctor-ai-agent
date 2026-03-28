"""
In-memory trace/span buffers, disk I/O, async disk writer, and pruning logic.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any, Deque, Dict, List, Optional

_obs_log = logging.getLogger("observability")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Global buffers and config
# ---------------------------------------------------------------------------

_INTERNAL_PATH_PREFIXES = ("/api/admin", "/api/manage")
_MAX_TRACES = 2000
_TRACE_BUFFER: Deque[TraceRecord] = deque(maxlen=_MAX_TRACES)
_MAX_SPANS = 10000
_SPAN_BUFFER: Deque[SpanRecord] = deque(maxlen=_MAX_SPANS)
_LOCK = Lock()

_PERSIST_DIR = Path(os.environ.get("OBSERVABILITY_DIR", str(Path(__file__).resolve().parents[3] / "logs")))
_PERSIST_TRACES_FILE = _PERSIST_DIR / "observability_traces.jsonl"
_PERSIST_SPANS_FILE = _PERSIST_DIR / "observability_spans.jsonl"
_TTL_DAYS = int(os.environ.get("OBSERVABILITY_TTL_DAYS", "7"))
_PRUNE_EVERY = 200
_LOADED = False
_SPAN_WRITE_QUEUE: "asyncio.Queue[tuple[Path, dict]] | None" = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Disk writer (background coroutine)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Load from disk / pruning
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Lazy load
# ---------------------------------------------------------------------------

def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    if not _persist_enabled():
        return
    _load_from_disk()
