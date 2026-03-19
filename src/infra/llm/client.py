"""
Chinese-focused LLM provider registry.

Only Qwen and DeepSeek models — optimized for Chinese medical content.
All providers use OpenAI-compatible API format.
"""

from __future__ import annotations

import os


def _get_providers() -> dict:
    """Build provider registry. Reads env vars at call time so that
    runtime.json overrides and .dev.sh env vars both take effect.

    Chinese-only: every provider defaults to a Qwen or DeepSeek model.
    """
    return {
        # ── Direct API providers ─────────────────────────────────────
        "deepseek": {
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        },

        # ── Inference clouds (Qwen/DeepSeek hosted) ──────────────────
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "model": os.environ.get("GROQ_MODEL", "qwen/qwen3-32b"),
        },
        "sambanova": {
            "base_url": "https://api.sambanova.ai/v1",
            "api_key_env": "SAMBANOVA_API_KEY",
            "model": os.environ.get("SAMBANOVA_MODEL", "Qwen2.5-72B-Instruct"),
        },
        "cerebras": {
            "base_url": "https://api.cerebras.ai/v1",
            "api_key_env": "CEREBRAS_API_KEY",
            "model": os.environ.get("CEREBRAS_MODEL", "qwen-3-32b"),
        },
        "siliconflow": {
            "base_url": "https://api.siliconflow.cn/v1",
            "api_key_env": "SILICONFLOW_API_KEY",
            "model": os.environ.get("SILICONFLOW_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
        },

        # ── Multi-model routers ──────────────────────────────────────
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "model": os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.5-9b"),
        },

        # ── China cloud providers ────────────────────────────────────
        "tencent_lkeap": {
            "base_url": os.environ.get(
                "TENCENT_LKEAP_BASE_URL",
                "https://api.lkeap.cloud.tencent.com/v1",
            ),
            "api_key_env": "TENCENT_LKEAP_API_KEY",
            "model": os.environ.get("TENCENT_LKEAP_MODEL", "deepseek-v3-1"),
        },

        # ── Local / self-hosted ──────────────────────────────────────
        "ollama": {
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            "api_key_env": "OLLAMA_API_KEY",
            "model": os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
        },
    }


# Backward compat — code that imports _PROVIDERS gets a snapshot.
# For fresh env var reads, use _get_providers() instead.
_PROVIDERS = _get_providers()
