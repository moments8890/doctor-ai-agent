from __future__ import annotations

import importlib
import os
import sys
from types import SimpleNamespace
from typing import Callable, List

import httpx
import pytest
from openai import APIConnectionError

from utils.app_config import AppConfig


class _FakeCompletions:
    def __init__(self, base_url: str, behavior: Callable[[str], None]):
        self._base_url = base_url
        self._behavior = behavior

    async def create(self, **kwargs):
        self._behavior(self._base_url)
        return {"ok": True}


class _FakeAsyncOpenAI:
    def __init__(self, *, base_url: str, api_key: str, behavior: Callable[[str], None]):
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
        fallback_url = "http://localhost:11434/v1"
        calls: List[str] = []

        def _behavior(base_url: str) -> None:
            calls.append(base_url)
            if base_url == bad_url:
                req = httpx.Request("POST", f"{bad_url}/chat/completions")
                raise APIConnectionError(request=req)

        monkeypatch.setitem(sys.modules, "jieba", SimpleNamespace(initialize=lambda: None))
        monkeypatch.setenv("OLLAMA_BASE_URL", bad_url)
        monkeypatch.setenv("OLLAMA_VISION_BASE_URL", bad_url)

        def _factory(*, base_url: str, api_key: str):
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
        fallback_url = "http://localhost:11434/v1"
        calls: List[str] = []

        def _behavior(base_url: str) -> None:
            calls.append(base_url)
            raise ValueError("invalid model")

        monkeypatch.setitem(sys.modules, "jieba", SimpleNamespace(initialize=lambda: None))

        def _factory(*, base_url: str, api_key: str):
            return _FakeAsyncOpenAI(base_url=base_url, api_key=api_key, behavior=_behavior)

        monkeypatch.setattr("openai.AsyncOpenAI", _factory)

        with pytest.raises(RuntimeError, match="non-connectivity error"):
            await main._warmup(_config(bad_url))

        assert calls == [bad_url]
        assert fallback_url not in calls
    finally:
        os.environ.clear()
        os.environ.update(env_before)
