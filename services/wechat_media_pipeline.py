from __future__ import annotations

import asyncio
from typing import Awaitable, Callable


SendMessageFn = Callable[[str, str], Awaitable[None]]
HandleIntentFn = Callable[[str, str], Awaitable[None]]
DownloadMediaFn = Callable[[str, str], Awaitable[bytes]]
ExtractImageFn = Callable[[bytes, str], Awaitable[str]]
ExtractPdfFn = Callable[[bytes], str]
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
            f"已收到《{filename or 'PDF文件'}》，但未提取到可读文本。请发送关键页面截图或粘贴主要内容。",
        )
        return

    preview = text[:80].replace("\n", " ")
    log(f"[PDF] extracted for {doctor_id}: {preview!r}")
    await handle_intent_bg(f"[PDF:{filename or 'uploaded.pdf'}]\n{text}", doctor_id)


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

    await send_customer_service_msg(
        doctor_id,
        f"已收到文件《{name or '文件'}》。当前自动处理支持文字/语音/图片/PDF；其他文件请发送关键内容文本。",
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
