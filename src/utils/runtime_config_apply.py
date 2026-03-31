"""Apply runtime config: push key/value pairs into os.environ."""
from __future__ import annotations

import os
from typing import Dict


async def apply_runtime_config(config: Dict[str, str]) -> None:
    """Save config to os.environ and invalidate LLM client caches."""
    for key, value in config.items():
        os.environ[key] = value

    # Invalidate LLM client caches so new keys/URLs take effect immediately
    try:
        from agent.llm import _client_cache, _instructor_cache
        _client_cache.clear()
        _instructor_cache.clear()
    except ImportError:
        pass
