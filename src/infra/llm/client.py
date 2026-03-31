"""
LLM provider registry — Qwen and DeepSeek models for Chinese medical content.

All providers use OpenAI-compatible API format.
Includes both China-based (prod) and US-based (local dev) providers.
"""

from __future__ import annotations

import os


def _get_providers() -> dict:
    """Build provider registry. Reads env vars at call time so that
    runtime.json overrides and cli.py env vars both take effect.
    """
    return {
        # ── Direct API providers ─────────────────────────────────────
        "deepseek": {
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "models": ["deepseek-chat", "deepseek-reasoner"],
        },

        # ── China inference clouds ───────────────────────────────────
        "siliconflow": {
            "base_url": "https://api.siliconflow.cn/v1",
            "api_key_env": "SILICONFLOW_API_KEY",
            "model": os.environ.get("SILICONFLOW_MODEL", "Qwen/Qwen2.5-72B-Instruct"),
            "models": [
                "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen3.5-27B", "Qwen/Qwen3.5-35B-A3B",
                "Qwen/Qwen3-32B", "Qwen/Qwen2.5-32B-Instruct",
            ],
        },

        # ── China cloud providers (Alibaba) ─────────────────────────
        "dashscope": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key_env": "DASHSCOPE_API_KEY",
            "model": os.environ.get("DASHSCOPE_MODEL", "qwen-plus"),
            "models": [
                "qwen-plus", "qwen-turbo", "qwen3.5-plus", "qwen-max",
                "qwen3-32b", "qwen3-30b-a3b",
            ],
        },

        # ── China cloud providers (Tencent) ─────────────────────────
        "tencent_lkeap": {
            "base_url": os.environ.get(
                "TENCENT_LKEAP_BASE_URL",
                "https://api.lkeap.cloud.tencent.com/v1",
            ),
            "api_key_env": "TENCENT_LKEAP_API_KEY",
            "model": os.environ.get("TENCENT_LKEAP_MODEL", "deepseek-v3.2"),
            "models": ["deepseek-v3.2", "deepseek-v3.1", "deepseek-v3", "deepseek-r1"],
        },

        # ── US inference clouds (local dev / free tier) ─────────────
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "model": os.environ.get("GROQ_MODEL", "qwen/qwen3-32b"),
            "models": ["qwen/qwen3-32b", "deepseek-r1-distill-qwen-32b", "qwen-qwq-32b"],
        },
        "sambanova": {
            "base_url": "https://api.sambanova.ai/v1",
            "api_key_env": "SAMBANOVA_API_KEY",
            "model": os.environ.get("SAMBANOVA_MODEL", "Qwen2.5-72B-Instruct"),
            "models": ["Qwen2.5-72B-Instruct", "Qwen3-32B", "DeepSeek-V3-0324"],
        },
        "cerebras": {
            "base_url": "https://api.cerebras.ai/v1",
            "api_key_env": "CEREBRAS_API_KEY",
            "model": os.environ.get("CEREBRAS_MODEL", "qwen-3-32b"),
            "models": ["qwen-3-32b", "qwen-2.5-32b"],
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "model": os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.5-9b"),
            "models": ["qwen/qwen3.5-9b", "qwen/qwen3-32b", "deepseek/deepseek-chat-v3-0324:free"],
        },

        # ── Local / self-hosted ──────────────────────────────────────
        "ollama": {
            "base_url": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            "api_key_env": "OLLAMA_API_KEY",
            "model": os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
            "models": ["qwen2.5:7b", "qwen2.5:14b", "qwen3:8b"],
        },
    }


# Backward compat — code that imports _PROVIDERS gets a snapshot.
# For fresh env var reads, use _get_providers() instead.
_PROVIDERS = _get_providers()
