"""
LLM-based PDF text extractor using Anthropic's native PDF document support.

Supports both digital and scanned PDFs without needing pdftotext/pdftoppm.
Activated when ANTHROPIC_API_KEY is set and PDF_LLM != "none".

Usage:
    result = await extract_text_from_pdf_llm(pdf_bytes)
    # Returns None if LLM is not configured — caller falls back to pdftotext.
"""

from __future__ import annotations

import base64
import os

from utils.log import log

_SYSTEM_PROMPT = (
    "你是一名医疗文档识别助手。请将 PDF 中所有临床文字原样提取为纯文本，"
    "保留所有数字、单位、药物名称、检验值和日期，不要添加解释，不要输出 JSON，只输出纯文本。"
)

_USER_PROMPT = "请提取此 PDF 文件中的所有临床文字内容。"


def _is_enabled() -> bool:
    """Return True if LLM PDF extraction is configured."""
    if os.environ.get("PDF_LLM", "").lower() == "none":
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


async def extract_text_from_pdf_llm(
    pdf_bytes: bytes,
    max_chars: int = 12000,
    model: str | None = None,
) -> str | None:
    """Extract text from PDF using Claude's native PDF support.

    Returns extracted text string, or None if LLM extraction is not
    configured (caller should fall back to pdftotext).
    """
    if not _is_enabled():
        return None

    if not pdf_bytes:
        return ""

    import anthropic

    resolved_model = (
        model
        or os.environ.get("PDF_LLM_MODEL", "claude-haiku-4-5-20251001")
    )

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    log(f"[PDF-LLM] model={resolved_model} pdf_size={len(pdf_bytes)} bytes")

    client = anthropic.AsyncAnthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        timeout=float(os.environ.get("PDF_LLM_TIMEOUT", "90")),
    )

    message = await client.messages.create(
        model=resolved_model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": _USER_PROMPT},
                ],
            }
        ],
    )

    text = (message.content[0].text if message.content else "").strip()
    log(f"[PDF-LLM] extracted {len(text)} chars: {text[:80]!r}")

    if max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars]

    return text
