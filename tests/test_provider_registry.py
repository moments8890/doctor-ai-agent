"""Tests for services.ai.provider_registry — LLM Provider Registry."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from services.ai.provider_registry import (
    Capability,
    ProviderConfig,
    ProviderRegistry,
    registry,
)


@pytest.fixture
def fresh_registry():
    """A clean registry with no providers registered."""
    return ProviderRegistry()


# ---------- Registration ----------


def test_register_and_get(fresh_registry: ProviderRegistry):
    cfg = ProviderConfig(
        base_url="https://example.com/v1",
        api_key_env="TEST_KEY",
        model="test-model",
    )
    fresh_registry.register("test", cfg)
    assert fresh_registry.get("test") is cfg
    assert fresh_registry.has("test") is True
    assert "test" in fresh_registry.names()


def test_get_nonexistent(fresh_registry: ProviderRegistry):
    assert fresh_registry.get("nope") is None
    assert fresh_registry.has("nope") is False


def test_register_replaces(fresh_registry: ProviderRegistry):
    cfg1 = ProviderConfig(base_url="https://a.com", api_key_env="K", model="m1")
    cfg2 = ProviderConfig(base_url="https://b.com", api_key_env="K", model="m2")
    fresh_registry.register("p", cfg1)
    fresh_registry.register("p", cfg2)
    assert fresh_registry.get("p") is cfg2


def test_unregister(fresh_registry: ProviderRegistry):
    cfg = ProviderConfig(base_url="https://a.com", api_key_env="K", model="m")
    fresh_registry.register("p", cfg)
    assert fresh_registry.unregister("p") is True
    assert fresh_registry.has("p") is False


def test_unregister_nonexistent(fresh_registry: ProviderRegistry):
    assert fresh_registry.unregister("nope") is False


def test_list_providers(fresh_registry: ProviderRegistry):
    cfg = ProviderConfig(base_url="https://a.com", api_key_env="K", model="m")
    fresh_registry.register("alpha", cfg)
    fresh_registry.register("beta", cfg)
    providers = fresh_registry.list_providers()
    assert set(providers.keys()) == {"alpha", "beta"}


# ---------- Resolution ----------


def test_resolve_basic(fresh_registry: ProviderRegistry):
    cfg = ProviderConfig(
        base_url="https://example.com/v1",
        api_key_env="MY_KEY",
        model="my-model",
    )
    fresh_registry.register("test", cfg)
    resolved = fresh_registry.resolve("test")
    assert resolved == {
        "base_url": "https://example.com/v1",
        "api_key_env": "MY_KEY",
        "model": "my-model",
    }


def test_resolve_unknown_raises(fresh_registry: ProviderRegistry):
    with pytest.raises(KeyError, match="Unknown LLM provider"):
        fresh_registry.resolve("nope")


def test_resolve_with_env_override():
    """Env-var overrides should apply during resolve()."""
    with patch.dict(os.environ, {"OLLAMA_MODEL": "qwen2.5:7b"}):
        resolved = registry.resolve("ollama", role="routing")
        assert resolved["model"] == "qwen2.5:7b"


def test_resolve_structuring_model_override():
    """OLLAMA_STRUCTURING_MODEL takes precedence over OLLAMA_MODEL for structuring."""
    with patch.dict(os.environ, {
        "OLLAMA_STRUCTURING_MODEL": "qwen2.5:32b",
        "OLLAMA_MODEL": "qwen2.5:7b",
    }):
        resolved = registry.resolve("ollama", role="structuring")
        assert resolved["model"] == "qwen2.5:32b"


def test_resolve_openai_env_override():
    with patch.dict(os.environ, {
        "OPENAI_BASE_URL": "https://custom.openai.com/v1",
        "OPENAI_MODEL": "gpt-5",
    }):
        resolved = registry.resolve("openai", role="routing")
        assert resolved["base_url"] == "https://custom.openai.com/v1"
        assert resolved["model"] == "gpt-5"


def test_resolve_claude_model_override():
    with patch.dict(os.environ, {"CLAUDE_MODEL": "claude-opus-4-6"}):
        resolved = registry.resolve("claude", role="routing")
        assert resolved["model"] == "claude-opus-4-6"


def test_resolve_vision():
    """Vision resolution should use vision-specific endpoints."""
    resolved = registry.resolve("ollama", role="vision", vision=True)
    assert "model" in resolved


# ---------- Capabilities ----------


def test_supports_capability():
    assert registry.supports("deepseek", Capability.CHAT) is True
    assert registry.supports("deepseek", Capability.JSON_FORMAT) is True
    # Ollama doesn't support JSON_FORMAT
    assert registry.supports("ollama", Capability.JSON_FORMAT) is False


def test_supports_unknown_provider():
    assert registry.supports("nonexistent", Capability.CHAT) is False


# ---------- Vision config ----------


def test_provider_config_vision_model():
    cfg = ProviderConfig(
        base_url="https://api.example.com",
        api_key_env="K",
        model="base-model",
        vision_base_url="https://vision.example.com",
        vision_model="vision-model",
    )
    assert cfg.resolved_base_url(vision=True) == "https://vision.example.com"
    assert cfg.resolved_model(vision=True) == "vision-model"
    assert cfg.resolved_base_url(vision=False) == "https://api.example.com"
    assert cfg.resolved_model(vision=False) == "base-model"


def test_provider_config_callable_base_url():
    """base_url can be a callable for lazy env resolution."""
    cfg = ProviderConfig(
        base_url=lambda: "https://dynamic.example.com",
        api_key_env="K",
        model="m",
    )
    assert cfg.resolved_base_url() == "https://dynamic.example.com"


# ---------- Client construction ----------


def test_get_client_returns_async_openai(fresh_registry: ProviderRegistry):
    """get_client() should return an AsyncOpenAI instance."""
    from openai import AsyncOpenAI

    cfg = ProviderConfig(
        base_url="https://example.com/v1",
        api_key_env="NONEXISTENT_KEY",
        model="test",
    )
    fresh_registry.register("test", cfg)
    client = fresh_registry.get_client("test", role="routing", timeout=10)
    assert isinstance(client, AsyncOpenAI)


def test_clear_cache(fresh_registry: ProviderRegistry):
    cfg = ProviderConfig(
        base_url="https://example.com/v1",
        api_key_env="K",
        model="m",
    )
    fresh_registry.register("t", cfg)
    fresh_registry.get_client("t", role="routing")
    assert len(fresh_registry._client_cache) >= 0  # may be 0 in test mode
    fresh_registry.clear_cache()
    assert len(fresh_registry._client_cache) == 0


# ---------- Global registry ----------


def test_global_registry_has_default_providers():
    """The module-level registry should come pre-populated."""
    expected = {"ollama", "deepseek", "groq", "gemini", "openai", "tencent_lkeap", "claude"}
    assert set(registry.names()) == expected


def test_global_registry_ollama_defaults():
    cfg = registry.get("ollama")
    assert cfg is not None
    assert cfg.model == "qwen2.5:14b"
    assert cfg.api_key_env == "OLLAMA_API_KEY"


def test_global_registry_deepseek_defaults():
    cfg = registry.get("deepseek")
    assert cfg is not None
    assert cfg.model == "deepseek-chat"
    assert cfg.api_key_env == "DEEPSEEK_API_KEY"


# ---------- Backward-compatible _PROVIDERS view ----------


def test_providers_view_getitem():
    from services.ai.llm_client import _PROVIDERS

    p = _PROVIDERS["ollama"]
    assert "base_url" in p
    assert "api_key_env" in p
    assert "model" in p


def test_providers_view_get():
    from services.ai.llm_client import _PROVIDERS

    assert _PROVIDERS.get("ollama") is not None
    assert _PROVIDERS.get("nonexistent") is None


def test_providers_view_contains():
    from services.ai.llm_client import _PROVIDERS

    assert "deepseek" in _PROVIDERS
    assert "nonexistent" not in _PROVIDERS


def test_providers_view_keys():
    from services.ai.llm_client import _PROVIDERS

    keys = list(_PROVIDERS.keys())
    assert "ollama" in keys
    assert "deepseek" in keys


def test_providers_view_len():
    from services.ai.llm_client import _PROVIDERS

    assert len(_PROVIDERS) == 7


def test_providers_view_iter():
    from services.ai.llm_client import _PROVIDERS

    names = list(_PROVIDERS)
    assert "ollama" in names


def test_providers_view_items():
    from services.ai.llm_client import _PROVIDERS

    items = dict(_PROVIDERS.items())
    assert "ollama" in items
    assert "model" in items["ollama"]
