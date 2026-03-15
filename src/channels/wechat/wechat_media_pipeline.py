"""
WeChat 媒体消息处理管道：协调图片/PDF/Word下载和意图处理的异步流水线。
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

import httpx

from utils.log import log as _log


def _media_get_url() -> str:
    if os.environ.get("WECHAT_KF_CORP_ID", "").strip():
        return "https://qyapi.weixin.qq.com/cgi-bin/media/get"
    return "https://api.weixin.qq.com/cgi-bin/media/get"


async def download_media(media_id: str, access_token: str) -> bytes:
    """Download any WeChat media file (image, PDF, Word, etc.) without audio conversion."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            _media_get_url(),
            params={"access_token": access_token, "media_id": media_id},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"WeChat media download failed: HTTP {resp.status_code}")
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            raise RuntimeError(f"WeChat media error: {resp.json()}")
        _log(f"[Media] downloaded {len(resp.content)} bytes, content-type={content_type!r}")
        return resp.content


SendMessageFn = Callable[[str, str], Awaitable[None]]
HandleIntentFn = Callable[[str, str], Awaitable[None]]
DownloadMediaFn = Callable[[str, str], Awaitable[bytes]]
ExtractImageFn = Callable[[bytes, str], Awaitable[str]]
ExtractPdfFn = Callable[[bytes], str]
ExtractWordFn = Callable[[bytes], str]
GetConfigFn = Callable[[], dict]
GetAccessTokenFn = Callable[[str, str], Awaitable[str]]
LogFn = Callable[[str], None]


async def handle_pdf_file_bg(
    media_id: str,
    filename: str,
    doctor_id: str,
    *,
    get_config: GetConfigFn,
    get_access_token: GetAccessTokenFn,
    download_media: DownloadMediaFn,
    extract_pdf_text: ExtractPdfFn,
    send_customer_service_msg: SendMessageFn,
    handle_intent_bg: HandleIntentFn,
    log: LogFn,
) -> None:
    cfg = get_config()
    try:
        access_token = await get_access_token(cfg["app_id"], cfg["app_secret"])
        raw_bytes = await download_media(media_id, access_token)
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, extract_pdf_text, raw_bytes)
    except Exception as e:
        log(f"[PDF] extraction FAILED: {e}")
        await send_customer_service_msg(doctor_id, "❌ PDF解析失败，请稍后重试。")
        return

    if not text.strip():
        await send_customer_service_msg(
            doctor_id,
            f"已收到《{filename or 'PDF'}》\n未提取到文字，请发截图或粘贴内容。",
        )
        return

    preview = text[:80].replace("\n", " ")
    log(f"[PDF] extracted for {doctor_id}: {preview!r}")
    await handle_intent_bg(f"[PDF:{filename or 'uploaded.pdf'}]\n{text}", doctor_id)


async def handle_word_file_bg(
    media_id: str,
    filename: str,
    doctor_id: str,
    *,
    get_config: GetConfigFn,
    get_access_token: GetAccessTokenFn,
    download_media: DownloadMediaFn,
    extract_word_text,  # Callable[[bytes], str]
    send_customer_service_msg: SendMessageFn,
    handle_intent_bg: HandleIntentFn,
    log: LogFn,
) -> None:
    cfg = get_config()
    try:
        access_token = await get_access_token(cfg["app_id"], cfg["app_secret"])
        raw_bytes = await download_media(media_id, access_token)
        import asyncio as _asyncio
        loop = _asyncio.get_running_loop()
        text = await loop.run_in_executor(None, extract_word_text, raw_bytes)
    except Exception as e:
        log(f"[Word] extraction FAILED: {e}")
        await send_customer_service_msg(doctor_id, "❌ Word文件解析失败，请稍后重试。")
        return

    if not text.strip():
        await send_customer_service_msg(
            doctor_id,
            f"已收到《{filename or 'Word文件'}》\n未提取到文字，请发截图或粘贴内容。",
        )
        return

    preview = text[:80].replace("\n", " ")
    log(f"[Word] extracted for {doctor_id}: {preview!r}")
    await handle_intent_bg(f"[Word:{filename or 'uploaded.docx'}]\n{text}", doctor_id)


async def handle_file_bg(
    media_id: str,
    filename: str,
    doctor_id: str,
    *,
    get_config: GetConfigFn,
    get_access_token: GetAccessTokenFn,
    download_media: DownloadMediaFn,
    send_customer_service_msg: SendMessageFn,
    handle_pdf_file_bg_fn: Callable[[str, str, str], Awaitable[None]],
    handle_word_file_bg_fn: Callable[[str, str, str], Awaitable[None]],
    log: LogFn,
) -> None:
    cfg = get_config()
    try:
        access_token = await get_access_token(cfg["app_id"], cfg["app_secret"])
        raw_bytes = await download_media(media_id, access_token)
    except Exception as e:
        log(f"[File] download FAILED: {e}")
        await send_customer_service_msg(doctor_id, "❌ 文件下载失败，请稍后重试。")
        return

    name = (filename or "").strip()
    is_pdf = name.lower().endswith(".pdf") or raw_bytes.startswith(b"%PDF")
    if is_pdf:
        await handle_pdf_file_bg_fn(media_id, name or "uploaded.pdf", doctor_id)
        return

    is_word = name.lower().endswith(".docx") or name.lower().endswith(".doc")
    if is_word:
        await handle_word_file_bg_fn(media_id, name or "uploaded.docx", doctor_id)
        return

    await send_customer_service_msg(
        doctor_id,
        f"已收到《{name or '文件'}》\n暂不支持此类型，请发文字描述。",
    )


async def handle_image_bg(
    media_id: str,
    doctor_id: str,
    *,
    get_config: GetConfigFn,
    get_access_token: GetAccessTokenFn,
    download_media: DownloadMediaFn,
    extract_image_text: ExtractImageFn,
    send_customer_service_msg: SendMessageFn,
    handle_intent_bg: HandleIntentFn,
    log: LogFn,
) -> None:
    cfg = get_config()
    try:
        access_token = await get_access_token(cfg["app_id"], cfg["app_secret"])
        raw_bytes = await download_media(media_id, access_token)
        text = await extract_image_text(raw_bytes, "image/jpeg")
        log(f"[Vision] extracted for {doctor_id}: {text[:80]!r}")
    except Exception as e:
        log(f"[Vision] extraction FAILED: {e}")
        await send_customer_service_msg(doctor_id, "❌ 图片识别失败，请稍后重试。")
        return

    await handle_intent_bg(f"[Image:ocr]\n{text}", doctor_id)


def preprocess_wechat_chat_export(
    text: str,
    sender_filter: str | None = None,
) -> str:
    """Parse a WeChat PC chat export and return clinical content as plain text.

    Delegates to the dedicated parser in wechat_chat_export.py which handles:
    - Personal and group chat formats
    - Sender identification and optional filtering
    - Clinical vs non-clinical message filtering
    - Timestamp preservation for date-boundary chunking

    Args:
        text: Raw WeChat export text.
        sender_filter: Only include messages from this sender name.
                       If None, include all senders' clinical messages.
    """
    from channels.wechat.wechat_chat_export import extract_clinical_text
    return extract_clinical_text(text, sender_filter=sender_filter)
