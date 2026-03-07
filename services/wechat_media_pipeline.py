from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


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

    await handle_intent_bg(text, doctor_id)


def preprocess_wechat_chat_export(text: str) -> str:
    """Strip WeChat chat export headers and normalize for clinical import.

    WeChat exports look like:
        2023-11-15
        张三（13800000000）: 头疼三天了
        医生: 有发烧吗？
        张三: 没有

    Returns cleaned text keeping meaningful content.
    """
    import re
    lines = text.splitlines()
    cleaned = []
    # Strip pure date lines (YYYY-MM-DD or YYYY/MM/DD)
    date_only = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}\s*$")
    # Strip timestamp lines (HH:MM or HH:MM:SS)
    time_only = re.compile(r"^\d{2}:\d{2}(:\d{2})?\s*$")
    # Strip phone numbers from speaker labels
    phone_strip = re.compile(r"（\d{7,15}）")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if date_only.match(line) or time_only.match(line):
            continue
        line = phone_strip.sub("", line)
        cleaned.append(line)
    return "\n".join(cleaned)
