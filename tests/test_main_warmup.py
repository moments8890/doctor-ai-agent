"""主应用启动预热测试：覆盖 Ollama 连接失败回退、健康检查快照和调度器清理任务的行为。"""

from __future__ import annotations

import importlib
import os
import sys
from types import SimpleNamespace
from typing import Callable, List
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIConnectionError
from starlette.requests import Request

from utils.app_config import AppConfig


class _FakeCompletions:
    def __init__(self, base_url: str, behavior: Callable[[str], None]):
        self._base_url = base_url
        self._behavior = behavior

    async def create(self, **kwargs):
        self._behavior(self._base_url)
        return {"ok": True}


class _FakeAsyncOpenAI:
    def __init__(self, *, base_url: str, api_key: str, behavior: Callable[[str], None], **_: object):
        self.chat = SimpleNamespace(
            completions=_FakeCompletions(base_url=base_url, behavior=behavior)
        )


def _load_main_module():
    if "main" in sys.modules:
        return importlib.reload(sys.modules["main"])
    return importlib.import_module("main")


def _config(base_url: str) -> AppConfig:
    return AppConfig.from_env(
        {
            "ROUTING_LLM": "ollama",
            "STRUCTURING_LLM": "deepseek",
            "OLLAMA_BASE_URL": base_url,
            "OLLAMA_MODEL": "qwen2.5:14b",
            "OLLAMA_API_KEY": "ollama",
        },
        env_source="test",
    )


@pytest.mark.asyncio
async def test_warmup_falls_back_on_connectivity_error(monkeypatch):
    env_before = os.environ.copy()
    try:
        main = _load_main_module()
        bad_url = "http://unreachable:11434/v1"
        fallback_url = "http://192.168.0.123:11434/v1"
        calls: List[str] = []

        def _behavior(base_url: str) -> None:
            calls.append(base_url)
            if base_url == bad_url:
                req = httpx.Request("POST", f"{bad_url}/chat/completions")
                raise APIConnectionError(request=req)

        monkeypatch.setitem(sys.modules, "jieba", SimpleNamespace(initialize=lambda: None))
        monkeypatch.setenv("OLLAMA_BASE_URL", bad_url)
        monkeypatch.setenv("OLLAMA_VISION_BASE_URL", bad_url)

        def _factory(*, base_url: str, api_key: str, **kwargs: object):
            return _FakeAsyncOpenAI(base_url=base_url, api_key=api_key, behavior=_behavior)

        monkeypatch.setattr("openai.AsyncOpenAI", _factory)

        await main._warmup(_config(bad_url))

        assert calls[:3] == [bad_url, bad_url, bad_url]
        assert calls[3] == fallback_url
        assert main.os.environ["OLLAMA_BASE_URL"] == fallback_url
        assert main.os.environ["OLLAMA_VISION_BASE_URL"] == fallback_url
    finally:
        os.environ.clear()
        os.environ.update(env_before)


@pytest.mark.asyncio
async def test_warmup_raises_on_non_connectivity_error(monkeypatch):
    env_before = os.environ.copy()
    try:
        main = _load_main_module()
        bad_url = "http://unreachable:11434/v1"
        fallback_url = "http://192.168.0.123:11434/v1"
        calls: List[str] = []

        def _behavior(base_url: str) -> None:
            calls.append(base_url)
            raise ValueError("invalid model")

        monkeypatch.setitem(sys.modules, "jieba", SimpleNamespace(initialize=lambda: None))

        def _factory(*, base_url: str, api_key: str, **kwargs: object):
            return _FakeAsyncOpenAI(base_url=base_url, api_key=api_key, behavior=_behavior)

        monkeypatch.setattr("openai.AsyncOpenAI", _factory)

        with pytest.raises(RuntimeError, match="non-connectivity error"):
            await main._warmup(_config(bad_url))

        assert calls == [bad_url]
        assert fallback_url not in calls
    finally:
        os.environ.clear()
        os.environ.update(env_before)


def test_conversation_turn_retention_days_parsing(monkeypatch):
    main = _load_main_module()
    monkeypatch.setenv("CONVERSATION_TURN_RETENTION_DAYS", "0")
    assert main._conversation_turn_retention_days() == 1
    monkeypatch.setenv("CONVERSATION_TURN_RETENTION_DAYS", "abc")
    assert main._conversation_turn_retention_days() == 1095


def test_session_cache_cleanup_parsing(monkeypatch):
    main = _load_main_module()
    monkeypatch.setenv("SESSION_CACHE_CLEANUP_INTERVAL_MINUTES", "0")
    assert main._session_cache_cleanup_interval_minutes() == 1
    monkeypatch.setenv("SESSION_CACHE_CLEANUP_INTERVAL_MINUTES", "abc")
    assert main._session_cache_cleanup_interval_minutes() == 10

    monkeypatch.setenv("SESSION_CACHE_MAX_IDLE_SECONDS", "12")
    assert main._session_cache_max_idle_seconds() == 60
    monkeypatch.setenv("SESSION_CACHE_MAX_IDLE_SECONDS", "abc")
    assert main._session_cache_max_idle_seconds() == 3600


def test_ollama_warmup_timeout_and_backoff_parsing(monkeypatch):
    main = _load_main_module()
    monkeypatch.setenv("OLLAMA_WARMUP_TIMEOUT_SECONDS", "7.5")
    assert main._ollama_warmup_timeout_seconds() == 7.5

    monkeypatch.setenv("OLLAMA_WARMUP_TIMEOUT_SECONDS", "0")
    assert main._ollama_warmup_timeout_seconds() == 10.0

    monkeypatch.setenv("OLLAMA_WARMUP_TIMEOUT_SECONDS", "bad")
    assert main._ollama_warmup_timeout_seconds() == 10.0

    assert main._ollama_warmup_backoff_seconds(1) == 1.0
    assert main._ollama_warmup_backoff_seconds(2) == 2.0
    assert main._ollama_warmup_backoff_seconds(3) == 4.0


@pytest.mark.asyncio
async def test_cleanup_old_conversation_turns_invokes_purge(monkeypatch):
    main = _load_main_module()
    mock_session = object()

    class _Ctx:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _Ctx())
    mock_purge = AsyncMock(return_value=3)
    monkeypatch.setattr(main, "purge_conversation_turns_before", mock_purge)

    await main._cleanup_old_conversation_turns()
    assert mock_purge.await_count == 1


@pytest.mark.asyncio
async def test_cleanup_inactive_session_cache_invokes_prune(monkeypatch):
    main = _load_main_module()
    mock_prune = MagicMock(return_value={"evicted_sessions": 1})
    monkeypatch.setattr(main, "prune_inactive_sessions", mock_prune)

    await main._cleanup_inactive_session_cache()
    assert mock_prune.call_count == 1


@pytest.mark.asyncio
async def test_health_snapshot_reports_ok(monkeypatch):
    main = _load_main_module()

    class _DB:
        async def execute(self, _stmt):
            return None

    class _Ctx:
        async def __aenter__(self):
            return _DB()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _Ctx())
    monkeypatch.setattr(main, "_scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(main, "_startup_ready", True)

    snapshot = await main._health_snapshot()
    assert snapshot["status"] == "ok"
    assert snapshot["checks"]["database"]["ok"] is True
    assert snapshot["checks"]["scheduler"]["ok"] is True
    assert snapshot["checks"]["startup"]["ok"] is True


@pytest.mark.asyncio
async def test_health_snapshot_reports_degraded_on_db_error(monkeypatch):
    main = _load_main_module()

    class _Ctx:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _Ctx())
    monkeypatch.setattr(main, "_scheduler", SimpleNamespace(running=True))
    monkeypatch.setattr(main, "_startup_ready", True)

    snapshot = await main._health_snapshot()
    assert snapshot["status"] == "degraded"
    assert snapshot["checks"]["database"]["ok"] is False
    assert "db down" in snapshot["checks"]["database"]["error"]


@pytest.mark.asyncio
async def test_readyz_503_when_not_ready(monkeypatch):
    main = _load_main_module()
    monkeypatch.setattr(main, "_startup_ready", False)
    monkeypatch.setattr(main, "_scheduler", SimpleNamespace(running=False))
    resp = await main.readyz()
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_domain_exception_handler_returns_structured_response():
    main = _load_main_module()
    req = Request({"type": "http", "method": "GET", "path": "/x", "headers": []})
    err = main.DomainError("bad", status_code=422, error_code="bad_input")
    resp = await main._handle_domain_error(req, err)
    assert resp.status_code == 422
