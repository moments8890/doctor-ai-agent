"""
统一入站消息类型和渠道适配器接口。

``Message`` is the channel-agnostic inbound message dataclass.
``ChannelAdapter`` Protocol defines the target adapter interface.

Current live usage (2026-03-13):
  - Web: ``WebAdapter.parse_inbound()`` is called in records.py chat_core.
  - WeChat: ``WeChatAdapter.format_reply()`` is called in wechat_flows.py.
  - Other adapter methods (send_reply, send_notification, get_history,
    WeChatAdapter.parse_inbound) are defined but not yet on the live
    request path.  WeChat inbound still starts directly in wechat.py,
    and voice has its own endpoint path in voice.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from services.domain.intent_handlers._types import HandlerResult


@dataclass
class Message:
    """Channel-agnostic inbound message.

    All channels normalize raw input into this type before entering the
    intent-classification workflow pipeline.

    Attributes:
        content_type: "text" | "voice" | "image" | "file"
        text: Normalized text (transcription, OCR result, or raw text).
        doctor_id: Resolved doctor identifier.
        channel: "web" | "wechat" | "voice" | future channels
        raw_payload: Original platform object (wechatpy msg, ChatInput, etc.)
        metadata: Extra channel-specific data (media_id, file_type, etc.)
        history: Conversation history (list of role/content dicts).
    """

    content_type: str          # "text" | "voice" | "image" | "file"
    text: str                  # normalized text
    doctor_id: str
    channel: str               # "web" | "wechat" | "voice"
    raw_payload: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: List[dict] = field(default_factory=list)


@runtime_checkable
class ChannelAdapter(Protocol):
    """Typing contract for channel adapters.

    Each channel (Web, WeChat, future Feishu/DingTalk) implements this
    interface.  No base-class inheritance required — structural subtyping
    via Protocol is sufficient.

    Methods:
        parse_inbound:    Platform payload → unified Message.
        format_reply:     HandlerResult → channel wire format.
        send_reply:       Deliver a reply to the user asynchronously.
        send_notification:Deliver a system notification to the user.
        get_history:      Retrieve recent conversation history.
    """

    @property
    def channel_name(self) -> str:
        """Short identifier: "web", "wechat", etc."""
        ...  # pragma: no cover

    async def parse_inbound(self, raw_request: Any) -> Message:
        """Parse a platform-specific request into a unified Message."""
        ...  # pragma: no cover

    async def format_reply(self, result: HandlerResult) -> Any:
        """Convert a HandlerResult to the channel's wire format.

        - Web: ``ChatResponse`` (JSON with pending metadata)
        - WeChat: plain-text string (≤600 chars, split if needed)
        """
        ...  # pragma: no cover

    async def send_reply(self, doctor_id: str, reply: str) -> None:
        """Deliver a text reply to the user.

        - Web: included in HTTP response (no-op here).
        - WeChat: pushed via customer service API.
        """
        ...  # pragma: no cover

    async def send_notification(self, doctor_id: str, notification: str) -> None:
        """Deliver a system notification (task reminder, follow-up alert).

        - Web: pushed via WebSocket or polling endpoint.
        - WeChat: pushed via template message or customer service API.
        """
        ...  # pragma: no cover

    async def get_history(self, doctor_id: str) -> List[dict]:
        """Retrieve recent conversation history for routing context.

        - Web: extracted from request body (passed in ``ChatInput.history``).
        - WeChat: reconstructed from session / turn log.
        """
        ...  # pragma: no cover
