"""
调试与可观测性端点：debug 日志、观测数据、路由指标等辅助接口。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Optional
import uuid

from fastapi import APIRouter, Header, Query

from services.observability.observability import (
    add_span,
    add_trace,
    clear_traces,
    get_latency_summary_scoped,
    get_recent_spans_scoped,
    get_recent_traces_scoped,
    get_slowest_spans_scoped,
    get_trace_timeline,
)
from routers.ui._utils import _require_ui_debug_access

router = APIRouter(tags=["ui"], include_in_schema=False)

_LOG_SOURCES: dict[str, str] = {
    "app": "logs/app.log",
    "tasks": "logs/tasks.log",
    "scheduler": "logs/scheduler.log",
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
    log_path = Path(_LOG_SOURCES.get(source, "logs/app.log"))
    if not log_path.exists():
        return {"lines": [], "source": source, "total": 0}
    level_tags = _LOG_LEVEL_TAGS.get(level.upper())  # None means ALL
    matching: list[str] = []
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.rstrip()
                if level_tags is None or any(tag in stripped for tag in level_tags):
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
    from services.observability.routing_metrics import get_metrics
    return get_metrics()


@router.post("/api/debug/routing-metrics/reset")
async def debug_routing_metrics_reset(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Reset routing counters to zero."""
    _require_ui_debug_access(x_debug_token)
    from services.observability.routing_metrics import reset
    reset()
    return {"ok": True}
