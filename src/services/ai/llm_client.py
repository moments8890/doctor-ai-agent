"""
多提供商 LLM 客户端注册表，统一管理 Ollama、DeepSeek 等端点配置。
"""

from __future__ import annotations

import os

# Shared provider registry.  Both the routing agent and the structuring service
# use the same set of OpenAI-compatible endpoints.
#
# NOTE: AsyncOpenAI is intentionally NOT imported here.  Each consumer module
# imports AsyncOpenAI directly so that test patches on
# ``services.ai.agent.AsyncOpenAI`` / ``services.ai.structuring.AsyncOpenAI``
# continue to intercept client construction correctly.
_PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.0-flash",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
    "ollama": {
        "base_url": os.environ.get("OLLAMA_BASE_URL", "http://192.168.0.123:11434/v1"),
        "api_key_env": "OLLAMA_API_KEY",
        "model": "qwen2.5:14b",
    },
    "openai": {
        "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o",
    },
    "tencent_lkeap": {
        "base_url": os.environ.get("TENCENT_LKEAP_BASE_URL", "https://api.lkeap.cloud.tencent.com/v1"),
        "api_key_env": "TENCENT_LKEAP_API_KEY",
        "model": os.environ.get("TENCENT_LKEAP_MODEL", "deepseek-v3-1"),
    },
    "claude": {
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
    },
}
