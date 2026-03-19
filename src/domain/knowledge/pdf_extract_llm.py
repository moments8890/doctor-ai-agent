"""
基于视觉 LLM 的 PDF 文字提取：将 PDF 页转为图片后送入视觉模型，提取临床文本。

LLM-based PDF text extractor using the OpenAI SDK (same provider config as vision.py).

Strategy: convert PDF pages to JPEG images via pdftoppm, then send all pages
as image_url blocks to the configured vision LLM in a single request.

Activated when PDF_LLM != "none" and pdftoppm is available.
Falls back to pdftotext if pdftoppm is missing or LLM is disabled.

Env vars (shared with vision.py):
    VISION_LLM          Provider: ollama | gemini | openai  (default: ollama)
    OLLAMA_VISION_MODEL / OLLAMA_BASE_URL / OLLAMA_API_KEY
    GEMINI_API_KEY / GEMINI_VISION_MODEL
    OPENAI_API_KEY

    PDF_LLM             Set to "none" to disable and force pdftotext fallback
    PDF_LLM_MAX_PAGES   Max pages to extract (default: 10)
    PDF_LLM_DPI         pdftoppm resolution in dpi (default: 120)
    PDF_LLM_TIMEOUT     Seconds before LLM call times out (default: 90)
"""

from __future__ import annotations

import base64
import os
import subprocess

from openai import AsyncOpenAI

from utils.pdf_utils import pdf_to_images
from utils.log import log

_SYSTEM_PROMPT = (
    "你是一名医疗文档识别助手。请将图片中所有临床文字原样提取为纯文本，"
    "保留所有数字、单位、药物名称、检验值和日期，不要添加解释，不要输出 JSON，只输出纯文本。"
)

_PROVIDERS = {
    "ollama": {
        "base_url": lambda: os.environ.get("OLLAMA_VISION_BASE_URL") or os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "api_key_env": "OLLAMA_API_KEY",
        "model_env": "OLLAMA_VISION_MODEL",
        "model_default": "qwen3-vl:8b",
    },
    "gemini": {
        "base_url": lambda: "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_VISION_MODEL",
        "model_default": "gemini-2.0-flash",
    },
    "openai": {
        "base_url": lambda: None,
        "api_key_env": "OPENAI_API_KEY",
        "model_env": None,
        "model_default": "gpt-4o-mini",
    },
}


def _is_enabled() -> bool:
    if os.environ.get("PDF_LLM", "").lower() == "none":
        return False
    try:
        subprocess.run(["pdftoppm", "-v"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _build_llm_client(provider_name: str) -> tuple["AsyncOpenAI", str]:
    """Construct the AsyncOpenAI client and model name for the given provider."""
    cfg = _PROVIDERS.get(provider_name, _PROVIDERS["ollama"])
    model = os.environ.get(cfg["model_env"] or "", "") or cfg["model_default"]
    api_key = os.environ.get(cfg["api_key_env"], "nokeyneeded")
    base_url = cfg["base_url"]()
    timeout = float(os.environ.get("PDF_LLM_TIMEOUT", "90"))
    client_kwargs: dict = {"api_key": api_key, "timeout": timeout, "max_retries": 0}
    if base_url:
        client_kwargs["base_url"] = base_url
    return AsyncOpenAI(**client_kwargs), model


def _build_page_content(page_images: list[bytes]) -> list[dict]:
    """Convert JPEG page bytes to image_url content blocks for the LLM."""
    content: list[dict] = []
    for img_bytes in page_images:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    content.append({"type": "text", "text": "请提取以上所有页面中的临床文字内容。"})
    return content


async def _call_vision_llm(
    client: "AsyncOpenAI",
    model: str,
    page_images: list[bytes],
    provider_name: str,
) -> str:
    """Send page images to the vision LLM and return the extracted text."""
    content = _build_page_content(page_images)
    _tag = f"[pdf-extract:{provider_name}:{model}]"
    log(f"{_tag} request: pages={len(page_images)}")
    completion = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_tokens=4096,
        temperature=0,
    )
    text = (completion.choices[0].message.content or "").strip()
    log(f"{_tag} response: {len(text)} chars: {text[:80]!r}")
    return text


async def extract_text_from_pdf_llm(
    pdf_bytes: bytes,
    max_chars: int = 12000,
) -> str | None:
    """Extract text from PDF pages using a vision LLM via the OpenAI SDK.

    Returns extracted text, or None if LLM extraction is disabled/unavailable
    (caller should fall back to pdftotext).
    """
    if not _is_enabled():
        return None
    if not pdf_bytes:
        return ""

    max_pages = int(os.environ.get("PDF_LLM_MAX_PAGES", "10"))
    dpi = int(os.environ.get("PDF_LLM_DPI", "120"))
    page_images = pdf_to_images(pdf_bytes, max_pages, dpi=dpi)
    if not page_images:
        log("[pdf-extract] pdftoppm produced no images — falling back")
        return None

    provider_name = os.environ.get("VISION_LLM", "ollama")
    # PHI egress gate: PDF page images contain clinical data.
    from infra.llm.egress import is_local_provider, check_cloud_egress
    if not is_local_provider(provider_name):
        check_cloud_egress(provider_name, "pdf_extraction")
    client, model = _build_llm_client(provider_name)
    text = await _call_vision_llm(client, model, page_images, provider_name)

    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars]
    return text
