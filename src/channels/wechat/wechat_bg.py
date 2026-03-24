"""
WeChat 后台任务与 WeCom KF 消息解析：知识自学习和消息类型工具函数。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from db.engine import AsyncSessionLocal
from utils.log import log


async def bg_auto_learn(doctor_id: str, text: str, record: object) -> None:
    """Run knowledge auto-learning in the background (non-blocking)."""
    from domain.knowledge.doctor_knowledge import maybe_auto_learn_knowledge
    try:
        async with AsyncSessionLocal() as session:
            await maybe_auto_learn_knowledge(
                session, doctor_id, text,
                structured_fields=record.model_dump(exclude_none=True),
            )
    except Exception as e:
        log(f"[WeChat] bg auto-learn FAILED doctor={doctor_id}: {e}")


def _wecom_kf_msg_to_text_extra(msg: Dict[str, Any], msgtype: str) -> str:
    """Handle link, weapp, video, merged_msg WeCom KF message types."""
    if msgtype == "link":
        link = msg.get("link") or {}
        title = str(link.get("title") or "").strip()
        url = str(link.get("url") or "").strip()
        return f"[链接消息] {title or url}".strip()
    if msgtype in ("weapp", "miniprogram"):
        app = msg.get("weapp") or msg.get("miniprogram") or {}
        title = str(app.get("title") or "").strip()
        page = str(app.get("pagepath") or "").strip()
        return f"[小程序消息] {title or page}".strip()
    if msgtype == "video":
        return "[视频消息]"
    if msgtype == "merged_msg":
        merged = msg.get("merged_msg") or {}
        title = str(merged.get("title") or "聊天记录").strip()
        return f"[合并消息] {title}"
    return ""


def wecom_kf_msg_to_text(msg: Dict[str, Any]) -> str:
    """Convert a WeCom KF message dict to a plain text string."""
    msgtype = str(msg.get("msgtype", "")).lower()
    if msgtype == "text":
        return str((msg.get("text") or {}).get("content") or "").strip()
    if msgtype == "voice":
        rec = str((msg.get("voice") or {}).get("recognition") or "").strip()
        return rec or "[语音消息]"
    if msgtype == "image":
        return "[图片消息]"
    if msgtype == "file":
        filename = str((msg.get("file") or {}).get("filename") or "").strip()
        return f"[文件消息]{(' ' + filename) if filename else ''}"
    if msgtype == "location":
        location = msg.get("location") or {}
        title = str(location.get("title") or location.get("name") or "").strip()
        addr = str(location.get("address") or "").strip()
        return f"[位置消息] {title or addr}".strip()
    return _wecom_kf_msg_to_text_extra(msg, msgtype)


def wecom_msg_is_processable(msg: Dict[str, Any]) -> bool:
    """Return True if the message contains content that can be routed to the intent pipeline."""
    msgtype = str(msg.get("msgtype", "")).lower()
    if msgtype in ("text", "location", "link", "weapp", "miniprogram"):
        return bool(wecom_kf_msg_to_text(msg))
    if msgtype in ("voice", "image", "file", "video", "merged_msg"):
        return True
    return bool(msgtype)


def wecom_msg_time(msg: Dict[str, Any]) -> int:
    """Extract message send timestamp as int (0 if unavailable)."""
    for key in ("send_time", "create_time", "msg_time"):
        raw = msg.get(key)
        try:
            t = int(raw or 0)
            if t > 0:
                return t
        except (TypeError, ValueError):
            continue
    return 0
