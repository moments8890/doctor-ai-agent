"""
图像文字提取服务，支持 Ollama/Gemini/OpenAI 视觉模型，用于化验单识别。
"""

from __future__ import annotations

import base64
import os

from openai import AsyncOpenAI

from infra.llm.resilience import call_with_retry_and_fallback
from utils.log import log

# Module-level singleton cache: one HTTP connection pool per provider.
_CLIENT_CACHE: dict[str, AsyncOpenAI] = {}

_PROVIDERS = {
    "ollama": {
        "base_url": os.environ.get("OLLAMA_VISION_BASE_URL") or os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key_env": "OLLAMA_API_KEY",
        "model_env": "OLLAMA_VISION_MODEL",
        "model_default": "qwen3-vl:8b",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_VISION_MODEL",
        "model_default": "gemini-2.0-flash",
    },
    "openai": {
        "base_url": None,  # default OpenAI endpoint
        "api_key_env": "OPENAI_API_KEY",
        "model_env": None,
        "model_default": "gpt-4o-mini",
    },
}


def _build_vision_client(provider_name: str) -> tuple[AsyncOpenAI, str]:
    """构造视觉 LLM 客户端，返回 (client, model_name)，使用模块级缓存。"""
    cfg = _PROVIDERS[provider_name]
    model = cfg["model_default"]
    if cfg["model_env"]:
        model = os.environ.get(cfg["model_env"], model)
    api_key = os.environ.get(cfg["api_key_env"], "nokeyneeded")
    client_kwargs: dict = {
        "api_key": api_key,
        "timeout": float(os.environ.get("VISION_LLM_TIMEOUT", "60")),
        "max_retries": 0,
    }
    if cfg["base_url"]:
        client_kwargs["base_url"] = cfg["base_url"]
    cache_key = f"{provider_name}:{model}"
    is_test = os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in os.environ.get("_", "")
    if cache_key not in _CLIENT_CACHE or is_test:
        _CLIENT_CACHE[cache_key] = AsyncOpenAI(**client_kwargs)
    return _CLIENT_CACHE[cache_key], model


def _build_vision_messages(data_url: str, vision_prompt: str) -> list:
    """构建图像提取请求的消息列表。"""
    return [
        {"role": "system", "content": vision_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": "请提取图片中所有临床文字。"},
            ],
        },
    ]


async def extract_text_from_image(image_bytes: bytes, mime_type: str) -> str:
    """Extract all clinical text from an image using a vision LLM.

    Provider is selected via the VISION_LLM env var (default: 'ollama').
    For ollama, the model is OLLAMA_VISION_MODEL (default: 'qwen3-vl:8b').
    """
    provider_name = os.environ.get("VISION_LLM", "ollama")
    # PHI egress gate: image bytes contain clinical data.
    from infra.llm.egress import is_local_provider, check_cloud_egress
    if not is_local_provider(provider_name):
        check_cloud_egress(provider_name, "vision_ocr")
    client, model = _build_vision_client(provider_name)
    _tag = f"[vision:{provider_name}:{model}]"
    log(f"{_tag} request: image_size={len(image_bytes)} bytes")

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{image_b64}"

    from utils.prompt_loader import get_prompt
    vision_prompt = await get_prompt("intent/vision-ocr")
    messages = _build_vision_messages(data_url, vision_prompt)

    async def _call(model_name: str):
        return await client.chat.completions.create(
            model=model_name, messages=messages, max_tokens=2000, temperature=0,
        )

    fallback_model = None
    if provider_name == "ollama":
        fallback_model = os.environ.get("OLLAMA_VISION_FALLBACK_MODEL", "qwen3-vl:8b")
    completion = await call_with_retry_and_fallback(
        _call,
        primary_model=model,
        fallback_model=fallback_model,
        max_attempts=int(os.environ.get("VISION_LLM_ATTEMPTS", "3")),
        op_name="vision.chat_completion",
    )

    extracted = (completion.choices[0].message.content or "").strip()
    log(f"{_tag} response: {len(extracted)} chars: {extracted[:80]!r}")
    if not extracted:
        raise RuntimeError("Vision LLM returned empty text — check image quality or model availability.")
    return extracted
