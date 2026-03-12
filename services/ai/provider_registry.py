"""LLM Provider Registry — single source of truth for all LLM endpoints.

Replaces the duplicated ``_PROVIDERS`` dicts scattered across ``llm_client.py``,
``intent.py``, ``vision.py``, and ``pdf_extract_llm.py``.

Usage::

    from services.ai.provider_registry import registry

    # Resolve a provider with env-var overrides applied
    cfg = registry.resolve("ollama", role="routing")

    # Get a cached AsyncOpenAI client
    client = registry.get_client("ollama", role="routing", timeout=45)

    # Register a custom provider
    registry.register("my_provider", ProviderConfig(
        base_url="https://my-api.example.com/v1",
        api_key_env="MY_API_KEY",
        model="my-model",
        capabilities=frozenset({Capability.CHAT, Capability.TOOLS}),
    ))
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, Optional, Union

from utils.log import log


class Capability(str, enum.Enum):
    """What a provider can do."""

    CHAT = "chat"
    TOOLS = "tools"
    VISION = "vision"
    JSON_FORMAT = "json_format"


_ALL_CHAT = frozenset({Capability.CHAT, Capability.TOOLS, Capability.JSON_FORMAT})
_CHAT_ONLY = frozenset({Capability.CHAT, Capability.TOOLS})


@dataclass(frozen=True)
class ProviderConfig:
    """Immutable configuration for one LLM provider endpoint."""

    base_url: Union[str, Callable[[], str]]  # str or lazy callable
    api_key_env: str
    model: str
    capabilities: FrozenSet[Capability] = field(default_factory=lambda: _ALL_CHAT)

    # Optional vision-specific overrides
    vision_base_url: Optional[Union[str, Callable[[], str]]] = None
    vision_model: Optional[str] = None

    def resolved_base_url(self, vision: bool = False) -> str:
        """Return the base_url string, calling the callable if needed."""
        url = self.vision_base_url if (vision and self.vision_base_url) else self.base_url
        return url() if callable(url) else url

    def resolved_model(self, vision: bool = False) -> str:
        """Return the model name, preferring vision model when applicable."""
        if vision and self.vision_model:
            return self.vision_model
        return self.model


# ---------------------------------------------------------------------------
# Environment-variable override rules per provider, keyed by role.
# Each rule maps: (env_var_name, config_field).
# ---------------------------------------------------------------------------
_ENV_OVERRIDES: Dict[str, Dict[str, list]] = {
    "ollama": {
        "routing": [
            ("OLLAMA_BASE_URL", "base_url"),
            ("OLLAMA_MODEL", "model"),
        ],
        "structuring": [
            ("OLLAMA_BASE_URL", "base_url"),
            ("OLLAMA_STRUCTURING_MODEL", "model"),
            ("OLLAMA_MODEL", "model"),  # fallback if STRUCTURING not set
        ],
        "vision": [
            ("OLLAMA_VISION_BASE_URL", "base_url"),
            ("OLLAMA_BASE_URL", "base_url"),
            ("OLLAMA_VISION_MODEL", "model"),
        ],
        "memory": [
            ("OLLAMA_BASE_URL", "base_url"),
            ("OLLAMA_MODEL", "model"),
        ],
    },
    "openai": {
        "_default": [
            ("OPENAI_BASE_URL", "base_url"),
            ("OPENAI_MODEL", "model"),
        ],
    },
    "tencent_lkeap": {
        "_default": [
            ("TENCENT_LKEAP_BASE_URL", "base_url"),
            ("TENCENT_LKEAP_MODEL", "model"),
        ],
    },
    "claude": {
        "_default": [
            ("CLAUDE_MODEL", "model"),
        ],
    },
    "gemini": {
        "vision": [
            ("GEMINI_VISION_MODEL", "model"),
        ],
    },
}


class ProviderRegistry:
    """Central registry for all LLM providers."""

    def __init__(self) -> None:
        self._providers: Dict[str, ProviderConfig] = {}
        self._client_cache: Dict[str, object] = {}

    # -- Registration -------------------------------------------------------

    def register(self, name: str, config: ProviderConfig) -> None:
        """Register or replace a provider configuration."""
        self._providers[name] = config

    def unregister(self, name: str) -> bool:
        """Remove a provider.  Returns True if it existed."""
        removed = name in self._providers
        self._providers.pop(name, None)
        # Evict any cached clients for this provider.
        keys_to_evict = [k for k in self._client_cache if k.startswith(f"{name}:")]
        for k in keys_to_evict:
            self._client_cache.pop(k, None)
        return removed

    # -- Query --------------------------------------------------------------

    def get(self, name: str) -> Optional[ProviderConfig]:
        """Return the raw config for *name*, or None."""
        return self._providers.get(name)

    def list_providers(self) -> Dict[str, ProviderConfig]:
        """Return a copy of the full registry."""
        return dict(self._providers)

    def has(self, name: str) -> bool:
        return name in self._providers

    def names(self) -> list:
        return list(self._providers.keys())

    # -- Resolution (applies env-var overrides) ----------------------------

    def resolve(
        self,
        name: str,
        *,
        role: str = "routing",
        vision: bool = False,
    ) -> Dict[str, str]:
        """Resolve a provider to a concrete dict with env-var overrides applied.

        Args:
            name: Provider name (e.g. "ollama", "deepseek").
            role: Usage context — "routing", "structuring", "vision", "memory".
                  Determines which env-var overrides apply.
            vision: If True, prefer vision-specific endpoints.

        Returns:
            dict with keys: "base_url", "api_key_env", "model".

        Raises:
            KeyError: If the provider is not registered.
        """
        cfg = self._providers.get(name)
        if cfg is None:
            allowed = ", ".join(sorted(self._providers.keys()))
            raise KeyError(f"Unknown LLM provider: {name} (registered: {allowed})")

        result = {
            "base_url": cfg.resolved_base_url(vision=vision),
            "api_key_env": cfg.api_key_env,
            "model": cfg.resolved_model(vision=vision),
        }

        # Apply env-var overrides for this provider + role.
        # For each field, the *first* matching env var wins (higher specificity
        # should be listed first in _ENV_OVERRIDES).
        overrides = _ENV_OVERRIDES.get(name, {})
        rules = overrides.get(role) or overrides.get("_default", [])
        applied: set = set()
        for env_var, config_field in rules:
            if config_field in applied:
                continue
            val = os.environ.get(env_var)
            if val:
                result[config_field] = val
                applied.add(config_field)

        return result

    # -- Client construction -----------------------------------------------

    def get_client(
        self,
        name: str,
        *,
        role: str = "routing",
        timeout: float = 45.0,
        vision: bool = False,
    ) -> object:
        """Return a cached ``AsyncOpenAI`` client for the given provider.

        Lazily imports ``openai.AsyncOpenAI`` to avoid import-time side effects
        and keep test mocking clean.

        Args:
            name: Provider name.
            role: Usage context for env-var overrides.
            timeout: Request timeout in seconds.
            vision: If True, use vision endpoints.

        Returns:
            An ``AsyncOpenAI`` instance (typed as ``object`` to avoid a
            hard import dependency at module level).
        """
        from openai import AsyncOpenAI

        resolved = self.resolve(name, role=role, vision=vision)
        cache_key = f"{name}:{role}:{vision}:{timeout}"

        # Always create fresh clients in test mode so mock patches work.
        is_test = os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", "")
        if is_test:
            extra_headers = {"anthropic-version": "2023-06-01"} if name == "claude" else {}
            return AsyncOpenAI(
                base_url=resolved["base_url"],
                api_key=os.environ.get(resolved["api_key_env"], "nokeyneeded"),
                timeout=timeout,
                max_retries=0,
                default_headers=extra_headers,
            )

        if cache_key not in self._client_cache:
            if len(self._client_cache) >= 20:
                # Evict oldest entry.
                self._client_cache.pop(next(iter(self._client_cache)))
            extra_headers = {"anthropic-version": "2023-06-01"} if name == "claude" else {}
            self._client_cache[cache_key] = AsyncOpenAI(
                base_url=resolved["base_url"],
                api_key=os.environ.get(resolved["api_key_env"], "nokeyneeded"),
                timeout=timeout,
                max_retries=0,
                default_headers=extra_headers,
            )

        return self._client_cache[cache_key]

    def clear_cache(self) -> None:
        """Evict all cached clients (useful in tests or config reload)."""
        self._client_cache.clear()

    # -- Capability check ---------------------------------------------------

    def supports(self, name: str, capability: Capability) -> bool:
        """Check if a provider supports a given capability."""
        cfg = self._providers.get(name)
        return cfg is not None and capability in cfg.capabilities


# ---------------------------------------------------------------------------
# Module-level singleton — the global registry.
# ---------------------------------------------------------------------------
registry = ProviderRegistry()


def _init_default_providers() -> None:
    """Populate the global registry with built-in providers."""
    registry.register("ollama", ProviderConfig(
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://192.168.0.123:11434/v1"),
        api_key_env="OLLAMA_API_KEY",
        model="qwen2.5:14b",
        capabilities=_CHAT_ONLY,
        vision_base_url=lambda: os.environ.get(
            "OLLAMA_VISION_BASE_URL",
            os.environ.get("OLLAMA_BASE_URL", "http://192.168.0.123:11434/v1"),
        ),
        vision_model="qwen2.5vl:7b",
    ))
    registry.register("deepseek", ProviderConfig(
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        model="deepseek-chat",
        capabilities=_ALL_CHAT,
    ))
    registry.register("groq", ProviderConfig(
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        model="llama-3.3-70b-versatile",
        capabilities=_ALL_CHAT,
    ))
    registry.register("gemini", ProviderConfig(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key_env="GEMINI_API_KEY",
        model="gemini-2.0-flash",
        capabilities=frozenset({Capability.CHAT, Capability.TOOLS, Capability.JSON_FORMAT, Capability.VISION}),
        vision_model="gemini-2.0-flash",
    ))
    registry.register("openai", ProviderConfig(
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_key_env="OPENAI_API_KEY",
        model="gpt-5-codex",
        capabilities=frozenset({Capability.CHAT, Capability.TOOLS, Capability.JSON_FORMAT, Capability.VISION}),
        vision_model="gpt-4o-mini",
    ))
    registry.register("tencent_lkeap", ProviderConfig(
        base_url=os.environ.get("TENCENT_LKEAP_BASE_URL", "https://api.lkeap.cloud.tencent.com/v1"),
        api_key_env="TENCENT_LKEAP_API_KEY",
        model=os.environ.get("TENCENT_LKEAP_MODEL", "deepseek-v3-1"),
        capabilities=_ALL_CHAT,
    ))
    registry.register("claude", ProviderConfig(
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
        capabilities=_ALL_CHAT,
    ))


_init_default_providers()
