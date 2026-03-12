"""WeChat channel adapter — asynchronous message queue with session locking.

Normalizes wechatpy message objects into ``Message`` and converts
``HandlerResult`` into plain-text reply strings (≤600 chars per message).
"""

from __future__ import annotations

from typing import Any, List, Optional

from services.domain.intent_handlers._types import HandlerResult
from services.domain.message import Message
from utils.log import log


# WeChat customer service API message limit.
_WECHAT_MSG_LIMIT = 600


class WeChatAdapter:
    """ChannelAdapter implementation for the WeChat / WeCom channel."""

    @property
    def channel_name(self) -> str:
        return "wechat"

    async def parse_inbound(self, raw_request: Any) -> Message:
        """Convert a wechatpy message object into a unified ``Message``.

        Args:
            raw_request: A wechatpy message object (TextMessage, VoiceMessage,
                         etc.) or a dict with ``content``, ``source``, ``type``.
        """
        # Support both wechatpy message objects and plain dicts.
        if isinstance(raw_request, dict):
            text = raw_request.get("content", "")
            doctor_id = raw_request.get("source", "unknown")
            msg_type = raw_request.get("type", "text")
            metadata = {k: v for k, v in raw_request.items()
                        if k not in ("content", "source", "type")}
        else:
            text = getattr(raw_request, "content", "") or ""
            doctor_id = getattr(raw_request, "source", "unknown")
            msg_type = getattr(raw_request, "type", "text")
            metadata = {}
            # Extract WeChat-specific fields.
            for attr in ("media_id", "recognition", "format",
                         "thumb_media_id", "location_x", "location_y"):
                val = getattr(raw_request, attr, None)
                if val is not None:
                    metadata[attr] = val

        # Map wechatpy message type to unified content_type.
        content_type_map = {
            "text": "text",
            "voice": "voice",
            "image": "image",
            "video": "file",
            "shortvideo": "file",
            "location": "text",
            "link": "text",
            "file": "file",
        }
        content_type = content_type_map.get(str(msg_type), "text")

        # For voice messages, use recognition field if available.
        if content_type == "voice" and metadata.get("recognition"):
            text = metadata["recognition"]

        return Message(
            content_type=content_type,
            text=text.strip() if text else "",
            doctor_id=doctor_id,
            channel="wechat",
            raw_payload=raw_request,
            metadata=metadata,
        )

    async def format_reply(self, result: HandlerResult) -> str:
        """Convert a HandlerResult to a plain-text reply string.

        If ``switch_notification`` is set, it is prepended as a separate line
        before the reply text (matches the legacy ``_hr_to_text`` behaviour).
        """
        parts = [p for p in (result.switch_notification, result.reply) if p]
        return "\n".join(parts)

    async def send_reply(self, doctor_id: str, reply: str) -> None:
        """Deferred — not wired into production.

        The actual WeChat customer-service API call is handled by
        ``services.wechat.wechat_notify._send_customer_service_msg()``.
        Callers should use that function directly until full adapter
        integration is complete.  This stub satisfies the
        ``ChannelAdapter`` protocol contract.
        """
        log(f"[WeChatAdapter] send_reply stub: doctor={doctor_id} len={len(reply)}")

    async def send_notification(
        self, doctor_id: str, notification: str, *, open_kfid: str = "",
    ) -> None:
        """Send a switch-notification (or other one-off notice) via the WeChat
        customer-service API so it appears as a separate chat bubble.

        Delegates to ``_send_customer_service_msg`` for the actual HTTP call.
        """
        from services.wechat.wechat_notify import (
            _send_customer_service_msg,
        )
        log(f"[WeChatAdapter] send_notification: doctor={doctor_id} len={len(notification)}")
        await _send_customer_service_msg(
            doctor_id, notification, open_kfid=open_kfid,
        )

    async def get_history(self, doctor_id: str) -> List[dict]:
        """Reconstruct history from session / turn log.

        In WeChat, history is not included in the request.  This method
        should reconstruct recent turns from the session service.
        """
        # Defer to session service — import lazily to avoid circular deps.
        try:
            from services.session import get_session
            sess = get_session(doctor_id)
            return getattr(sess, "conversation_history", []) or []
        except Exception:
            return []


def split_wechat_message(text: str, limit: int = _WECHAT_MSG_LIMIT) -> List[str]:
    """Split a long message into chunks respecting the WeChat character limit.

    Splits on newlines first, then by character count.
    """
    if not text or len(text) <= limit:
        return [text] if text else []

    chunks: List[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # If single line exceeds limit, hard-split.
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
    if current:
        chunks.append(current)
    return chunks
