"""
WeCom 企业微信客服消息类型处理器：按消息类型分发处理逻辑。
"""

from __future__ import annotations

import json
from typing import Any, Dict

from channels.wechat.wecom_kf_sync import (
    HandleFileFn,
    HandleImageFn,
    HandleIntentFn,
    LogFn,
    MsgTimeFn,
    MsgToTextFn,
    SendMessageFn,
)


async def _handle_voice_msg(
    selected: Dict[str, Any],
    external_userid: str,
    open_kfid: str,
    msg_id: str,
    send_customer_service_msg: SendMessageFn,
    handle_intent_bg: HandleIntentFn,
    log: LogFn,
) -> None:
    """处理语音消息：使用平台 ASR 文字，无 ASR 则告知不支持。"""
    voice = selected.get("voice") or {}
    recognition = str(voice.get("recognition") or "").strip()
    if recognition:
        await handle_intent_bg(recognition, external_userid, open_kfid)
        log(
            f"[WeCom KF] queued voice(recognition) user={external_userid} kf={open_kfid} "
            f"msgid={msg_id or 'n/a'} text={recognition[:80]!r}"
        )
        return
    await send_customer_service_msg(
        external_userid,
        "暂不支持语音消息，请发送文字或图片。",
        open_kfid,
    )


async def _handle_image_msg(
    selected: Dict[str, Any],
    external_userid: str,
    open_kfid: str,
    msg_id: str,
    send_customer_service_msg: SendMessageFn,
    handle_image_bg: HandleImageFn,
    log: LogFn,
) -> None:
    """处理图片消息：通知用户后异步 OCR。"""
    image = selected.get("image") or {}
    media_id = str(image.get("media_id") or "").strip()
    if media_id:
        await send_customer_service_msg(external_userid, "已收到图片，正在识别文字，请稍候。", open_kfid)
        await handle_image_bg(media_id, external_userid, open_kfid)
        log(
            f"[WeCom KF] queued image(media) user={external_userid} kf={open_kfid} "
            f"msgid={msg_id or 'n/a'} media_id={media_id}"
        )
        return
    await send_customer_service_msg(
        external_userid,
        "已收到图片，但未拿到图片文件ID，暂时无法解析。请重试发送。",
        open_kfid,
    )


async def _handle_file_msg(
    selected: Dict[str, Any],
    external_userid: str,
    open_kfid: str,
    msg_id: str,
    send_customer_service_msg: SendMessageFn,
    handle_file_bg: HandleFileFn,
    log: LogFn,
) -> None:
    """处理文件消息：通知用户后异步解析。"""
    filename = str((selected.get("file") or {}).get("filename") or "文件").strip()
    media_id = str((selected.get("file") or {}).get("media_id") or "").strip()
    if media_id:
        await send_customer_service_msg(
            external_userid,
            f"已收到文件《{filename}》，正在识别并处理，请稍候。",
            open_kfid,
        )
        await handle_file_bg(media_id, filename, external_userid, open_kfid)
    else:
        await send_customer_service_msg(
            external_userid,
            f"已收到文件《{filename}》，但未拿到文件ID，暂时无法解析。请重试或改发图片/文本。",
            open_kfid,
        )
    log(
        f"[WeCom KF] file received user={external_userid} kf={open_kfid} "
        f"msgid={msg_id or 'n/a'} filename={filename!r} media_id={media_id or 'n/a'}"
    )


async def _handle_merged_msg(
    selected: Dict[str, Any],
    external_userid: str,
    open_kfid: str,
    msg_id: str,
    send_customer_service_msg: SendMessageFn,
    handle_intent_bg: HandleIntentFn,
    log: LogFn,
) -> None:
    """处理合并转发消息：提取文字部分后分发意图处理。"""
    merged = selected.get("merged_msg") or {}
    items = merged.get("item") or []
    parts: list[str] = []
    for item in items:
        item_type = str(item.get("msgtype") or "").lower()
        sender = str(item.get("sender_name") or item.get("from_name") or "").strip()
        if item_type == "text":
            raw = item.get("msg_content") or ""
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
                content = str((parsed.get("text") or {}).get("content") or "").strip()
            except Exception:
                content = str(raw).strip()
            if not content:
                content = str((item.get("text") or {}).get("content") or "").strip()
            if content:
                parts.append(f"{sender}：{content}" if sender else content)
    if parts:
        merged_text = "\n".join(parts)
        await handle_intent_bg(merged_text, external_userid, open_kfid)
        log(
            f"[WeCom KF] merged_msg extracted {len(parts)} text items "
            f"user={external_userid} kf={open_kfid} msgid={msg_id or 'n/a'}"
        )
    else:
        await send_customer_service_msg(
            external_userid,
            "已收到合并转发消息，但未找到可提取的文字内容，请改发文字描述。",
            open_kfid,
        )
        log(
            f"[WeCom KF] merged_msg no text items user={external_userid} kf={open_kfid} msgid={msg_id or 'n/a'}"
        )


async def _handle_video_msg(
    external_userid: str,
    open_kfid: str,
    msg_id: str,
    send_customer_service_msg: SendMessageFn,
    log: LogFn,
) -> None:
    """处理视频消息：告知用户暂不支持。"""
    await send_customer_service_msg(
        external_userid,
        "已收到视频。当前暂不支持自动转写视频，请发送关键内容文字说明，我可继续处理。",
        open_kfid,
    )
    log(f"[WeCom KF] video received user={external_userid} kf={open_kfid} msgid={msg_id or 'n/a'}")


async def _handle_text_or_unknown(
    text: str,
    msgtype: str,
    external_userid: str,
    open_kfid: str,
    msg_id: str,
    expected_msgid: str,
    event_create_time: int,
    msg_time_val: int,
    send_customer_service_msg: SendMessageFn,
    handle_intent_bg: HandleIntentFn,
    log: LogFn,
) -> None:
    """处理文本或不支持的消息类型。"""
    if not text:
        await send_customer_service_msg(
            external_userid,
            f"已收到消息类型：{msgtype or 'unknown'}，当前暂不支持自动处理，请改发文字描述。",
            open_kfid,
        )
        return
    await handle_intent_bg(text, external_userid, open_kfid)
    log(
        f"[WeCom KF] queued inbound text user={external_userid} kf={open_kfid} "
        f"msgid={msg_id or 'n/a'} expected_msgid={expected_msgid or 'n/a'} "
        f"event_create_time={event_create_time or 0} msg_time={msg_time_val} text={text!r}"
    )


async def dispatch_message(
    selected: Dict[str, Any],
    msg_id: str,
    external_userid: str,
    open_kfid: str,
    expected_msgid: str,
    event_create_time: int,
    msg_time: MsgTimeFn,
    send_customer_service_msg: SendMessageFn,
    handle_image_bg: HandleImageFn,
    handle_file_bg: HandleFileFn,
    handle_intent_bg: HandleIntentFn,
    msg_to_text: MsgToTextFn,
    log: LogFn,
) -> None:
    """根据消息类型分发到对应处理函数。"""
    msgtype = str(selected.get("msgtype") or "").lower()
    text = msg_to_text(selected)
    if msgtype == "voice":
        await _handle_voice_msg(
            selected, external_userid, open_kfid, msg_id,
            send_customer_service_msg, handle_intent_bg, log,
        )
    elif msgtype == "image":
        await _handle_image_msg(
            selected, external_userid, open_kfid, msg_id,
            send_customer_service_msg, handle_image_bg, log,
        )
    elif msgtype == "file":
        await _handle_file_msg(
            selected, external_userid, open_kfid, msg_id,
            send_customer_service_msg, handle_file_bg, log,
        )
    elif msgtype == "video":
        await _handle_video_msg(external_userid, open_kfid, msg_id, send_customer_service_msg, log)
    elif msgtype == "merged_msg":
        await _handle_merged_msg(
            selected, external_userid, open_kfid, msg_id,
            send_customer_service_msg, handle_intent_bg, log,
        )
    else:
        await _handle_text_or_unknown(
            text, msgtype, external_userid, open_kfid, msg_id,
            expected_msgid, event_create_time, msg_time(selected),
            send_customer_service_msg, handle_intent_bg, log,
        )
