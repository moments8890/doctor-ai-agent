"""
调试与可观测性端点：debug 日志、观测数据、路由指标等辅助接口。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Header, Query
from fastapi.responses import FileResponse

from infra.observability.observability import (
    add_span,
    add_trace,
    clear_traces,
    get_latency_summary_scoped,
    get_recent_spans_scoped,
    get_recent_traces_scoped,
    get_slowest_spans_scoped,
    get_trace_timeline,
)
from channels.web.ui._utils import _require_ui_debug_access

router = APIRouter(tags=["ui"], include_in_schema=False)

_LOG_ROOT = str(Path(__file__).resolve().parents[4] / "logs")
_LOG_SOURCES: dict[str, str] = {
    "app": f"{_LOG_ROOT}/app.log",
    "tasks": f"{_LOG_ROOT}/tasks.log",
    "scheduler": f"{_LOG_ROOT}/scheduler.log",
}

_LOG_LEVEL_TAGS: dict[str, list[str]] = {
    "DEBUG": ["[DEBUG]", "[INFO]", "[WARNING]", "[ERROR]", "[CRITICAL]"],
    "INFO": ["[INFO]", "[WARNING]", "[ERROR]", "[CRITICAL]"],
    "WARNING": ["[WARNING]", "[ERROR]", "[CRITICAL]"],
    "ERROR": ["[ERROR]", "[CRITICAL]"],
    "CRITICAL": ["[CRITICAL]"],
}


@router.get("/api/debug/logs")
async def debug_logs(
    level: str = Query(default="ALL", description="Filter level: ALL, DEBUG, INFO, WARNING, ERROR, CRITICAL"),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    source: str = Query(default="app", description="Log source: app, tasks, scheduler"),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Return recent log lines filtered by level (hierarchical: WARNING includes ERROR, CRITICAL)."""
    _require_ui_debug_access(x_debug_token)
    log_path = Path(_LOG_SOURCES.get(source, f"{_LOG_ROOT}/app.log"))
    if not log_path.exists():
        return {"lines": [], "source": source, "total": 0}
    level_upper = level.upper()
    level_priority = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_priority = level_priority.get(level_upper, -1)  # -1 means ALL
    matching: list[str] = []
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.rstrip()
                if not stripped:
                    continue
                if min_priority >= 0:
                    # Try JSON parse first (new format)
                    try:
                        obj = json.loads(stripped)
                        line_level = obj.get("level", "info").upper()
                        if level_priority.get(line_level, 0) >= min_priority:
                            matching.append(stripped)
                        continue
                    except (json.JSONDecodeError, ValueError):
                        pass
                    # Fall back to text tag matching (old format lines still in log)
                    if any(tag in stripped for tag in _LOG_LEVEL_TAGS.get(level_upper, [])):
                        matching.append(stripped)
                else:
                    matching.append(stripped)
    except OSError:
        return {"lines": [], "source": source, "total": 0}
    return {"lines": matching[-limit:], "source": source, "total": len(matching)}


@router.get("/api/debug/observability")
async def debug_observability(
    trace_limit: int = Query(default=80, ge=1, le=500),
    summary_limit: int = Query(default=500, ge=1, le=2000),
    span_limit: int = Query(default=300, ge=1, le=1000),
    slow_span_limit: int = Query(default=30, ge=1, le=200),
    scope: str = Query(default="public"),
    trace_id: str | None = Query(default=None),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Observability data for the debug page."""
    _require_ui_debug_access(x_debug_token)
    return {
        "summary": get_latency_summary_scoped(limit=summary_limit, scope=scope),
        "recent_traces": get_recent_traces_scoped(limit=trace_limit, scope=scope),
        "recent_spans": get_recent_spans_scoped(limit=span_limit, scope=scope, trace_id=trace_id),
        "slow_spans": get_slowest_spans_scoped(limit=slow_span_limit, scope=scope),
        "trace_timeline": get_trace_timeline(trace_id=trace_id) if trace_id else [],
    }


@router.delete("/api/debug/observability/traces")
async def debug_clear_observability_traces(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Clear in-memory observability traces."""
    _require_ui_debug_access(x_debug_token)
    clear_traces()
    return {"ok": True}


@router.post("/api/debug/observability/sample")
async def debug_seed_observability_samples(
    count: int = Query(default=3, ge=1, le=20),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Seed sample observability data for testing."""
    _require_ui_debug_access(x_debug_token)
    now = datetime.now(timezone.utc)
    created: list[str] = []
    for i in range(count):
        trace_id = str(uuid.uuid4())
        created.append(trace_id)
        started = now - timedelta(seconds=(count - i))
        total_ms = 1200.0 + i * 180.0
        llm_ms = max(200.0, total_ms - 180.0)
        status_code = 200 if i % 4 != 3 else 500
        add_trace(
            trace_id=trace_id, started_at=started, method="POST",
            path="/api/records/chat", status_code=status_code, latency_ms=total_ms,
        )
        add_span(
            trace_id=trace_id, parent_span_id=None, layer="router",
            name="records.chat.agent_dispatch", started_at=started,
            latency_ms=llm_ms + 12.0,
            status="ok" if status_code < 500 else "error", meta={"sample": True},
        )
        add_span(
            trace_id=trace_id, parent_span_id=None, layer="llm",
            name="agent.chat_completion",
            started_at=started + timedelta(milliseconds=6),
            latency_ms=llm_ms,
            status="ok" if status_code < 500 else "error", meta={"provider": "sample"},
        )
    return {"ok": True, "count": len(created)}


@router.get("/api/debug/routing-metrics")
async def debug_routing_metrics(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Fast-router vs LLM hit counts for the debug page."""
    _require_ui_debug_access(x_debug_token)
    from infra.observability.routing_metrics import get_metrics
    return get_metrics()


@router.post("/api/debug/routing-metrics/reset")
async def debug_routing_metrics_reset(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Reset routing counters to zero."""
    _require_ui_debug_access(x_debug_token)
    from infra.observability.routing_metrics import reset
    reset()
    return {"ok": True}


_LLM_LOG_FILE = Path(__file__).resolve().parents[4] / "logs" / "llm_calls.jsonl"


@router.get("/api/debug/llm-calls")
async def debug_llm_calls(
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    op: Optional[str] = Query(default=None),
    doctor_id: Optional[str] = Query(default=None),
    trace_id: Optional[str] = Query(default=None),
    since_minutes: int = Query(default=60, ge=1, le=1440),
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Return recent LLM calls with filtering. Reads tail of llm_calls.jsonl."""
    _require_ui_debug_access(x_debug_token)
    if not _LLM_LOG_FILE.exists():
        return {"calls": [], "total": 0, "has_more": False}

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    cutoff_iso = cutoff.isoformat()

    # Read from end of file for speed — only read last chunk
    _MAX_READ_BYTES = 512 * 1024  # 512 KB tail, enough for ~200 recent calls
    matching: list[dict] = []
    try:
        file_size = _LLM_LOG_FILE.stat().st_size
        read_start = max(0, file_size - _MAX_READ_BYTES) if not trace_id else 0  # full scan for trace_id lookup
        with open(_LLM_LOG_FILE, encoding="utf-8", errors="replace") as fh:
            if read_start > 0:
                fh.seek(read_start)
                fh.readline()  # skip partial first line after seek
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = entry.get("timestamp", "")
                if ts < cutoff_iso:
                    continue
                if op and entry.get("op") != op:
                    continue
                if doctor_id and entry.get("doctor_id") != doctor_id:
                    continue
                if trace_id and entry.get("trace_id") != trace_id:
                    continue
                matching.append(entry)
    except OSError:
        return {"calls": [], "total": 0, "has_more": False}

    total = len(matching)
    # Newest first, then paginate
    matching.reverse()
    page = matching[offset:offset + limit]
    has_more = (offset + limit) < total
    return {"calls": page, "total": total, "has_more": has_more}


@router.get("/debug", include_in_schema=False)
async def debug_dashboard_page(token: str = Query(..., description="Debug access token")):
    """Serve the debug dashboard HTML page. Token required."""
    _require_ui_debug_access(token)
    return FileResponse(
        Path(__file__).parent / "debug.html",
        media_type="text/html",
    )
