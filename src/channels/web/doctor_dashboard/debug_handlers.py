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
from channels.web.doctor_dashboard.deps import _require_ui_debug_access

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
                if op:
                    entry_op = entry.get("op", "")
                    if entry_op != op and not entry_op.startswith(op + "."):
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


@router.get("/api/debug/dashboard", include_in_schema=False)
async def debug_dashboard_page(token: str = Query(..., description="Debug access token")):
    """Serve the debug dashboard HTML page. Token required."""
    _require_ui_debug_access(token)
    return FileResponse(
        Path(__file__).parent / "debug.html",
        media_type="text/html",
    )


@router.get("/debug", include_in_schema=False)
async def debug_page_shortcut(token: str = Query(..., description="Debug access token")):
    """Short URL alias for the debug dashboard HTML page. Token required."""
    _require_ui_debug_access(token)
    return FileResponse(
        Path(__file__).parent / "debug.html",
        media_type="text/html",
    )


_LLM_PRICING: dict[str, dict] = {
    "deepseek": {"input": 2.0, "output": 8.0, "unit": "RMB/M tokens", "note": "cache hit: 0.1 input"},
    "tencent_lkeap": {"input": 2.0, "output": 8.0, "unit": "RMB/M tokens", "note": "deepseek-v3.2"},
    "dashscope": {"input": 0.8, "output": 2.0, "unit": "RMB/M tokens", "note": "qwen-plus"},
    "siliconflow": {"input": 4.13, "output": 4.13, "unit": "RMB/M tokens", "note": "Qwen2.5-72B"},
}


@router.get("/api/debug/llm-providers")
async def llm_providers(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """List all configured LLM providers with their status."""
    import os
    _require_ui_debug_access(x_debug_token)
    from infra.llm.client import _get_providers

    providers = _get_providers()
    active = os.environ.get("ROUTING_LLM", "")
    structuring = os.environ.get("STRUCTURING_LLM", "")
    diagnosis = os.environ.get("DIAGNOSIS_LLM", "")

    result = []
    for name, pcfg in providers.items():
        api_key = os.environ.get(pcfg.get("api_key_env", ""), "")
        has_key = bool(api_key) and name != "ollama"
        roles = []
        if name == active:
            roles.append("routing")
        if name == structuring:
            roles.append("structuring")
        if name == diagnosis:
            roles.append("diagnosis")
        result.append({
            "name": name,
            "model": pcfg["model"],
            "models": pcfg.get("models", [pcfg["model"]]),
            "base_url": pcfg["base_url"],
            "configured": has_key,
            "active": name == active,
            "roles": roles,
            "pricing": _LLM_PRICING.get(name, {}),
        })
    return {"providers": result, "active": active}


_BENCH_TIMEOUT_S = 5  # per-call hard timeout


@router.post("/api/debug/llm-benchmark")
async def llm_benchmark(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
    runs: int = Query(default=2, ge=1, le=5),
    providers_csv: str = Query(default="", alias="providers", description="Comma-separated provider names to test. Empty = all configured."),
    models_csv: str = Query(default="", alias="models", description="Comma-separated model overrides per provider (same order as providers). Empty = use default."),
):
    """Run latency benchmark for selected LLM providers.

    Tests with a realistic ~3K token medical prompt using streaming.
    All providers run in parallel; each call has a 5s hard timeout.
    """
    import asyncio
    import os
    import time
    from openai import AsyncOpenAI

    _require_ui_debug_access(x_debug_token)

    from infra.llm.client import _get_providers

    MESSAGES = [
        {"role": "system", "content": "你是一位专业的神经外科医生AI助手，负责帮助医生采集和结构化病历信息。" * 50},
        {"role": "user", "content": "患者男50岁，头痛3天加重1天，伴恶心呕吐，既往高血压10年，请给出鉴别诊断"},
    ]

    providers = _get_providers()
    active = os.environ.get("ROUTING_LLM", "")
    selected = [p.strip() for p in providers_csv.split(",") if p.strip()] if providers_csv else None
    model_overrides_list = [m.strip() for m in models_csv.split(",") if m.strip()] if models_csv else []
    # Map provider → override model (by position)
    model_overrides: dict[str, str] = {}
    if selected and model_overrides_list:
        for i, name in enumerate(selected):
            if i < len(model_overrides_list) and model_overrides_list[i]:
                model_overrides[name] = model_overrides_list[i]

    async def _single_run(client: AsyncOpenAI, model: str, run_idx: int) -> dict:
        t0 = time.monotonic()
        ttft = None
        chunks = 0
        error_msg = None

        async def _do():
            nonlocal ttft, chunks
            _m = model.lower()
            extra = {"enable_thinking": False} if ("qwen3" in _m or "qwen-3" in _m) else None
            stream = await client.chat.completions.create(
                model=model, messages=MESSAGES, max_tokens=150, stream=True, extra_body=extra,
            )
            async for chunk in stream:
                if ttft is None and chunk.choices and chunk.choices[0].delta.content:
                    ttft = int((time.monotonic() - t0) * 1000)
                if chunk.choices and chunk.choices[0].delta.content:
                    chunks += 1

        try:
            await asyncio.wait_for(_do(), timeout=_BENCH_TIMEOUT_S)
            total = int((time.monotonic() - t0) * 1000)
        except asyncio.TimeoutError:
            total = int((time.monotonic() - t0) * 1000)
            error_msg = f"timeout ({_BENCH_TIMEOUT_S}s)"
        except Exception as e:
            total = int((time.monotonic() - t0) * 1000)
            error_msg = str(e)[:120]
        return {"run": run_idx + 1, "ttft_ms": ttft, "total_ms": total,
                "chunks": chunks, "error": error_msg}

    async def _bench_provider(name: str, pcfg: dict) -> dict:
        client = AsyncOpenAI(
            base_url=pcfg["base_url"],
            api_key=os.environ.get(pcfg.get("api_key_env", ""), ""),
            timeout=60,  # generous HTTP timeout; _BENCH_TIMEOUT_S enforced via asyncio
        )
        model = model_overrides.get(name, pcfg["model"])
        run_results = [await _single_run(client, model, i) for i in range(runs)]

        valid = [r for r in run_results if r["ttft_ms"] is not None]
        avg_runs = valid[1:] if len(valid) > 1 else valid
        avg_ttft = int(sum(r["ttft_ms"] for r in avg_runs) / len(avg_runs)) if avg_runs else None
        avg_total = int(sum(r["total_ms"] for r in avg_runs) / len(avg_runs)) if avg_runs else None
        return {"provider": name, "model": model, "active": name == active,
                "avg_ttft_ms": avg_ttft, "avg_total_ms": avg_total, "runs": run_results}

    # Build tasks for all selected providers, run in parallel
    tasks = {}
    for name, pcfg in providers.items():
        api_key = os.environ.get(pcfg.get("api_key_env", ""), "")
        if not api_key or name == "ollama":
            continue
        if selected and name not in selected:
            continue
        tasks[name] = asyncio.create_task(_bench_provider(name, pcfg))

    results = list(await asyncio.gather(*tasks.values(), return_exceptions=True))
    # Replace any unexpected exceptions with error entries
    final = []
    for name, res in zip(tasks.keys(), results):
        if isinstance(res, Exception):
            final.append({"provider": name, "model": providers[name]["model"],
                          "active": name == active, "avg_ttft_ms": None,
                          "avg_total_ms": None, "runs": [{"run": 1, "error": str(res)[:120]}]})
        else:
            final.append(res)

    final.sort(key=lambda r: r["avg_ttft_ms"] if r["avg_ttft_ms"] is not None else 999999)
    return {"results": final, "active_provider": active, "prompt_tokens": "~3000"}


# ── Sim Eval ────────────────────────────────────────────────────────────────
# Loads real production-style scenarios from JSON fixtures.
# Tests routing, extraction, diagnosis, triage, and followup reply.

import re as _re

_THINK_STRIP = _re.compile(r"<think>.*?</think>\s*", _re.DOTALL)
_SCENARIOS_PATH = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "llm_eval" / "scenarios.json"


def _strip_llm(raw: str) -> str:
    """Strip <think> blocks and markdown fences from LLM output."""
    text = _THINK_STRIP.sub("", raw).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _load_eval_scenarios() -> list[dict]:
    """Load eval scenarios from fixture file, injecting cache-busting randomness."""
    import random
    if not _SCENARIOS_PATH.exists():
        return []
    scenarios = json.loads(_SCENARIOS_PATH.read_text(encoding="utf-8"))
    # Inject a unique nonce into each scenario's system message to prevent
    # provider-side prompt caching from inflating benchmark results.
    nonce = f"[eval-run-{random.randint(10000,99999)}]"
    for s in scenarios:
        msgs = s.get("messages", [])
        if msgs and msgs[0].get("role") == "system":
            msgs[0]["content"] = msgs[0]["content"] + f"\n\n<!-- {nonce} -->"
    return scenarios


def _check_scenario(scenario: dict, parsed, raw_output: str) -> tuple[bool, str]:
    """Validate LLM output against scenario checks. Returns (passed, reason)."""
    checks = scenario.get("check_fields", {})
    keywords = scenario.get("check_keywords", [])
    max_len = scenario.get("check_max_length")
    flat = json.dumps(parsed, ensure_ascii=False) if parsed else raw_output

    # Field checks
    for field_path, expected in checks.items():
        value = parsed
        for part in field_path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break
        if expected == "non_empty":
            if not value:
                return False, f"field '{field_path}' empty"
        elif expected == "non_empty_array":
            if not isinstance(value, list) or len(value) == 0:
                return False, f"field '{field_path}' not non-empty array"
        elif value != expected:
            return False, f"field '{field_path}': got {value!r}, expected {expected!r}"

    # Keyword checks
    for kw in keywords:
        if kw not in flat:
            return False, f"keyword '{kw}' missing"

    # Length check (for followup replies)
    if max_len and len(raw_output) > max_len:
        return False, f"output too long ({len(raw_output)} > {max_len})"

    return True, ""


@router.get("/api/debug/llm-eval/scenarios")
async def llm_eval_scenarios(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
):
    """Return eval scenario metadata for display (no LLM calls)."""
    _require_ui_debug_access(x_debug_token)
    scenarios = _load_eval_scenarios()
    items = []
    for s in scenarios:
        user_msgs = [m["content"] for m in s["messages"] if m["role"] == "user"]
        sys_msgs = [m["content"] for m in s["messages"] if m["role"] == "system"]
        total_chars = sum(len(m["content"]) for m in s["messages"])
        check_json = s.get("check_json", False)
        check_fields = list(s.get("check_fields", {}).keys())
        output_fmt = "JSON" if check_json else "text"
        if check_json and check_fields:
            output_fmt = "JSON {" + ", ".join(check_fields) + "}"
        items.append({
            "id": s["id"],
            "task": s.get("task", ""),
            "description": s.get("description", ""),
            "input": user_msgs[-1][:300] if user_msgs else "",
            "system_prompt_preview": sys_msgs[0][:200] + "..." if sys_msgs else "",
            "input_chars": total_chars,
            "input_tokens_est": total_chars // 2,  # rough CJK estimate
            "output_format": output_fmt,
            "checks": {
                "json": check_json,
                "fields": check_fields,
                "keywords": s.get("check_keywords", []),
                "max_length": s.get("check_max_length"),
            },
        })
    return {"scenarios": items}


@router.post("/api/debug/llm-eval")
async def llm_eval(
    x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
    providers_csv: str = Query(default="", alias="providers"),
    models_csv: str = Query(default="", alias="models"),
):
    """Run multi-scenario eval across provider+model combos.

    Loads real production-style scenarios from tests/fixtures/llm_eval/scenarios.json.
    Tests routing, extraction, diagnosis, triage, followup with actual prompt formats.
    All combos run in parallel. Returns pass/fail + latency per scenario.
    """
    import asyncio
    import os
    import time
    from openai import AsyncOpenAI

    _require_ui_debug_access(x_debug_token)
    from infra.llm.client import _get_providers

    scenarios = _load_eval_scenarios()
    if not scenarios:
        return {"results": [], "scenario_count": 0, "error": "No scenarios found"}

    providers = _get_providers()
    selected = [p.strip() for p in providers_csv.split(",") if p.strip()] if providers_csv else None
    model_overrides_list = [m.strip() for m in models_csv.split(",") if m.strip()] if models_csv else []
    model_overrides: dict[str, str] = {}
    if selected and model_overrides_list:
        for i, name in enumerate(selected):
            if i < len(model_overrides_list) and model_overrides_list[i]:
                model_overrides[name] = model_overrides_list[i]

    def _needs_nothink(model: str) -> bool:
        m = model.lower()
        return "qwen3" in m or "qwen-3" in m

    async def _eval_one(client: AsyncOpenAI, model: str, scenario: dict) -> dict:
        t0 = time.monotonic()
        error_msg = None
        raw_output = ""
        parsed = None
        passed = False
        reason = ""

        messages = scenario["messages"]
        extra = {"enable_thinking": False} if _needs_nothink(model) else None
        check_json = scenario.get("check_json", True)

        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model, messages=messages, max_tokens=800, extra_body=extra,
                ),
                timeout=20,
            )
            raw_output = (resp.choices[0].message.content or "").strip()
            text = _strip_llm(raw_output)

            if check_json:
                parsed = json.loads(text)
            else:
                parsed = None  # free-text output (e.g. followup reply)

            passed, reason = _check_scenario(scenario, parsed, raw_output)
        except asyncio.TimeoutError:
            error_msg = "timeout (20s)"
        except json.JSONDecodeError:
            error_msg = "JSON parse failed"
        except Exception as e:
            error_msg = str(e)[:150]

        # Extract last user message as the test input
        user_msgs = [m["content"] for m in scenario["messages"] if m["role"] == "user"]
        input_text = user_msgs[-1] if user_msgs else ""

        return {
            "scenario_id": scenario["id"],
            "task": scenario["task"],
            "description": scenario.get("description", ""),
            "input": input_text[:200],
            "total_ms": int((time.monotonic() - t0) * 1000),
            "passed": passed,
            "error": error_msg,
            "reason": reason,
            "raw_output": raw_output[:600],
        }

    async def _eval_provider(name: str, pcfg: dict) -> dict:
        model = model_overrides.get(name, pcfg["model"])
        client = AsyncOpenAI(
            base_url=pcfg["base_url"],
            api_key=os.environ.get(pcfg.get("api_key_env", ""), ""),
            timeout=60,
        )
        scenario_results = []
        for s in scenarios:
            r = await _eval_one(client, model, s)
            scenario_results.append(r)

        passed = sum(1 for r in scenario_results if r["passed"])
        total = len(scenario_results)
        avg_ms = int(sum(r["total_ms"] for r in scenario_results) / total) if total else 0
        return {
            "provider": name,
            "model": model,
            "score": f"{passed}/{total}",
            "passed": passed,
            "total": total,
            "avg_ms": avg_ms,
            "scenarios": scenario_results,
        }

    # Run all providers in parallel
    tasks = {}
    for name, pcfg in providers.items():
        api_key = os.environ.get(pcfg.get("api_key_env", ""), "")
        if not api_key or name == "ollama":
            continue
        if selected and name not in selected:
            continue
        tasks[name] = asyncio.create_task(_eval_provider(name, pcfg))

    raw_results = list(await asyncio.gather(*tasks.values(), return_exceptions=True))
    final = []
    for name, res in zip(tasks.keys(), raw_results):
        if isinstance(res, Exception):
            final.append({"provider": name, "model": providers[name]["model"],
                          "score": "0/0", "passed": 0, "total": 0, "avg_ms": 0,
                          "scenarios": [], "error": str(res)[:150]})
        else:
            final.append(res)

    final.sort(key=lambda r: (-r["passed"], r["avg_ms"]))
    return {"results": final, "scenario_count": len(scenarios)}
