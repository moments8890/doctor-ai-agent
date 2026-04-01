"""Apply runtime config: push key/value pairs into os.environ.

Mirrors the startup merge logic in main.py: env vars set externally
(e.g. shell exports, cli.py) take precedence over config-file values.
"""
from __future__ import annotations

import os
from typing import Dict


async def apply_runtime_config(config: Dict[str, str]) -> None:
    """Save config to os.environ and invalidate LLM client caches.

    For each key, the existing env var takes precedence when the config-file
    value is empty but the env var is non-empty.  This prevents an empty
    ``runtime.json`` field from clobbering a real API key injected via the
    process environment.
    """
    for key, value in config.items():
        str_value = str(value) if value is not None else ""
        existing = os.environ.get(key, "")
        # Config file value wins when non-empty; otherwise keep existing env var
        if str_value:
            os.environ[key] = str_value
        elif not existing:
            # Both empty — still set so the key exists in environ
            os.environ[key] = str_value

    # Invalidate LLM client caches so new keys/URLs take effect immediately
    try:
        from agent.llm import _client_cache, _instructor_cache
        _client_cache.clear()
        _instructor_cache.clear()
    except ImportError:
        pass
