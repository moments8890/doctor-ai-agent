"""可观测性模块测试：验证链路追踪记录、延迟统计、Span 嵌套及请求中间件的追踪行为。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional
from unittest.mock import patch

import pytest
from fastapi.responses import JSONResponse
from starlette.requests import Request

import main
import services.observability.observability as observability


def _request(path: str, method: str = "GET", trace_id: Optional[str] = None) -> Request:
    headers = []
    if trace_id:
        headers.append((b"x-trace-id", trace_id.encode("utf-8")))
    scope: Dict = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_get_recent_traces_newest_first_with_limit():
    observability.clear_traces()
    now = datetime.now(timezone.utc)
    observability.add_trace("t1", now, "GET", "/a", 200, 10.0)
    observability.add_trace("t2", now, "GET", "/b", 201, 20.0)
    observability.add_trace("t3", now, "POST", "/c", 500, 30.0)

    rows = observability.get_recent_traces(limit=2)
    assert len(rows) == 2
    assert rows[0]["trace_id"] == "t3"
    assert rows[1]["trace_id"] == "t2"


def test_get_latency_summary_contains_percentiles_status_and_path_stats():
    observability.clear_traces()
    now = datetime.now(timezone.utc)
    observability.add_trace("t1", now, "GET", "/p1", 200, 10.0)
    observability.add_trace("t2", now, "GET", "/p1", 200, 20.0)
    observability.add_trace("t3", now, "GET", "/p2", 500, 30.0)
    observability.add_trace("t4", now, "GET", "/p2", 500, 100.0)

    summary = observability.get_latency_summary(limit=10)
    assert summary["count"] == 4
    assert summary["avg_ms"] == 40.0
    assert summary["max_ms"] == 100.0
    assert summary["p50_ms"] == 20.0
    assert summary["p95_ms"] == 30.0
    assert summary["p99_ms"] == 30.0
    assert summary["status_counts"] == {"200": 2, "500": 2}
    assert summary["per_path"]["/p1"] == {"count": 2, "avg_ms": 15.0, "max_ms": 20.0}
    assert summary["per_path"]["/p2"] == {"count": 2, "avg_ms": 65.0, "max_ms": 100.0}


def test_clear_traces_removes_all_rows():
    observability.clear_traces()
    observability.add_trace("t1", datetime.now(timezone.utc), "GET", "/a", 200, 1.0)
    assert observability.get_latency_summary(limit=10)["count"] == 1
    observability.clear_traces()
    assert observability.get_recent_traces(limit=10) == []
    assert observability.get_latency_summary(limit=10)["count"] == 0


def test_trace_block_records_span_with_context_and_parent():
    observability.clear_traces()
    trace_token = observability.set_current_trace_id("trace-span-1")
    try:
        with observability.trace_block("router", "chat"):
            with observability.trace_block("llm", "completion"):
                pass
    finally:
        observability.reset_current_trace_id(trace_token)

    spans = observability.get_recent_spans(limit=10, trace_id="trace-span-1")
    assert len(spans) == 2
    parent = spans[0]
    child = spans[1]
    assert child["name"] == "completion"
    assert child["parent_span_id"] == parent["span_id"]
    assert child["trace_id"] == "trace-span-1"
    assert child["latency_ms"] >= 0.0


def test_slowest_spans_and_timeline():
    observability.clear_traces()
    now = datetime.now(timezone.utc)
    observability.add_span("trace-a", "db", "query_fast", now, 10.0, status="ok")
    observability.add_span("trace-a", "llm", "query_slow", now, 150.0, status="ok")
    observability.add_span("trace-b", "router", "query_mid", now, 50.0, status="error")

    slow = observability.get_slowest_spans(limit=2)
    assert slow[0]["name"] == "query_slow"
    assert slow[1]["name"] == "query_mid"

    timeline = observability.get_trace_timeline("trace-a", limit=10)
    assert len(timeline) == 2
    assert all(row["trace_id"] == "trace-a" for row in timeline)


def test_scoped_trace_and_span_views_public_vs_internal():
    observability.clear_traces()
    now = datetime.now(timezone.utc)
    observability.add_trace("tp", now, "POST", "/api/records/chat", 200, 100.0)
    observability.add_trace("ti", now, "GET", "/api/admin/observability", 200, 5.0)
    observability.add_span("tp", "llm", "agent.chat_completion", now, 90.0, status="ok")
    observability.add_span("ti", "router", "admin_observability", now, 2.0, status="ok")

    public_summary = observability.get_latency_summary_scoped(limit=10, scope="public")
    internal_summary = observability.get_latency_summary_scoped(limit=10, scope="internal")
    assert public_summary["count"] == 1
    assert internal_summary["count"] == 1
    assert observability.get_recent_traces_scoped(limit=10, scope="public")[0]["trace_id"] == "tp"
    assert observability.get_recent_traces_scoped(limit=10, scope="internal")[0]["trace_id"] == "ti"

    public_spans = observability.get_recent_spans_scoped(limit=10, scope="public")
    internal_spans = observability.get_recent_spans_scoped(limit=10, scope="internal")
    assert len(public_spans) == 1 and public_spans[0]["trace_id"] == "tp"
    assert len(internal_spans) == 1 and internal_spans[0]["trace_id"] == "ti"


async def test_trace_requests_middleware_records_success_and_sets_header():
    request = _request("/api/manage/patients", trace_id="trace-123")

    async def call_next(_request):
        return JSONResponse({"ok": True}, status_code=201)

    with patch("main.add_trace") as add_trace_mock:
        response = await main.trace_requests_middleware(request, call_next)

    assert response.status_code == 201
    assert response.headers["X-Trace-Id"] == "trace-123"
    add_trace_mock.assert_called_once()
    kwargs = add_trace_mock.call_args.kwargs
    assert kwargs["trace_id"] == "trace-123"
    assert kwargs["method"] == "GET"
    assert kwargs["path"] == "/api/manage/patients"
    assert kwargs["status_code"] == 201
    assert kwargs["latency_ms"] >= 0.0


async def test_trace_requests_middleware_records_exception_as_500():
    request = _request("/api/fail")

    async def call_next(_request):
        raise RuntimeError("boom")

    with patch("main.add_trace") as add_trace_mock:
        with pytest.raises(RuntimeError):
            await main.trace_requests_middleware(request, call_next)

    add_trace_mock.assert_called_once()
    kwargs = add_trace_mock.call_args.kwargs
    assert kwargs["path"] == "/api/fail"
    assert kwargs["status_code"] == 500
    assert kwargs["latency_ms"] >= 0.0
