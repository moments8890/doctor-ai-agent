from __future__ import annotations

import base64
import os

from openai import AsyncOpenAI

from utils.log import log

_SYSTEM_PROMPT = (
    "你是一名医疗文档识别助手。请将图片中所有临床文字原样提取为纯文本，"
    "保留所有数字、单位和药物名称，不要添加解释，不要输出 JSON，只输出纯文本。"
)

_PROVIDERS = {
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "model_env": "OLLAMA_VISION_MODEL",
        "model_default": "qwen2.5vl:7b",
    },
    "openai": {
        "base_url": None,  # default OpenAI endpoint
        "api_key_env": "OPENAI_API_KEY",
        "model_env": None,
        "model_default": "gpt-4o-mini",
    },
}


async def extract_text_from_image(image_bytes: bytes, mime_type: str) -> str:
    """Extract all clinical text from an image using a vision LLM.

    Provider is selected via the VISION_LLM env var (default: 'ollama').
    For ollama, the model is OLLAMA_VISION_MODEL (default: 'qwen2.5vl:7b').
    """
    provider_name = os.environ.get("VISION_LLM", "ollama")
    cfg = _PROVIDERS[provider_name]

    model = cfg["model_default"]
    if cfg["model_env"]:
        model = os.environ.get(cfg["model_env"], model)

    api_key = os.environ.get(cfg["api_key_env"], "nokeyneeded")

    client_kwargs: dict = {"api_key": api_key}
    if cfg["base_url"]:
        client_kwargs["base_url"] = cfg["base_url"]

    client = AsyncOpenAI(**client_kwargs)

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:{mime_type};base64,{image_b64}"

    log(f"[Vision:{provider_name}] model={model} image_size={len(image_bytes)} bytes")

    completion = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                    {
                        "type": "text",
                        "text": "请提取图片中所有临床文字。",
                    },
                ],
            },
        ],
        max_tokens=2000,
        temperature=0,
    )

    extracted = (completion.choices[0].message.content or "").strip()
    log(f"[Vision:{provider_name}] extracted {len(extracted)} chars: {extracted[:80]!r}")

    if not extracted:
        raise RuntimeError("Vision LLM returned empty text — check image quality or model availability.")

    return extracted
