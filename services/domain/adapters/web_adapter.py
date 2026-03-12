"""Web channel adapter — synchronous HTTP request/response cycle.

Normalizes ``ChatInput`` Pydantic models into ``Message`` and converts
``HandlerResult`` into ``ChatResponse`` JSON.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from services.domain.chat_constants import VOICE_TRANSCRIPTION_PREFIX_RE
from services.domain.intent_handlers._types import HandlerResult
from services.domain.message import Message


class WebAdapter:
    """ChannelAdapter implementation for the Web / mini-program channel."""

    @property
    def channel_name(self) -> str:
        return "web"

    async def parse_inbound(self, raw_request: Any) -> Message:
        """Convert a ``ChatInput`` body into a unified ``Message``.

        Args:
            raw_request: A dict-like or Pydantic model with ``text``,
                         ``history``, ``doctor_id``.
        """
        text = getattr(raw_request, "text", "") or ""
        doctor_id = getattr(raw_request, "doctor_id", "unknown")
        raw_history = getattr(raw_request, "history", []) or []

        # Strip voice-transcription prefix (e.g. "语音转文字：...")
        text = VOICE_TRANSCRIPTION_PREFIX_RE.sub("", text).strip()

        # Normalize history to list[dict]
        history = []
        for h in raw_history:
            if isinstance(h, dict):
                history.append(h)
            else:
                history.append({
                    "role": getattr(h, "role", "user"),
                    "content": getattr(h, "content", ""),
                })

        return Message(
            content_type="text",
            text=text,
            doctor_id=doctor_id,
            channel="web",
            raw_payload=raw_request,
            history=history,
        )

    async def format_reply(self, result: HandlerResult) -> dict:
        """Convert a HandlerResult to a JSON-serializable dict.

        The caller (router) wraps this in a ``ChatResponse`` Pydantic model.
        """
        return {
            "reply": result.reply,
            "switch_notification": result.switch_notification,
            "record": result.record,
            "pending_id": result.pending_id,
            "pending_patient_name": result.pending_patient_name,
            "pending_expires_at": result.pending_expires_at,
        }

    async def send_reply(self, doctor_id: str, reply: str) -> None:
        """Deferred — not wired into production.

        Web replies are included in the synchronous HTTP response cycle;
        there is no async push mechanism yet.  This stub exists to satisfy
        the ``ChannelAdapter`` protocol and will be implemented when the
        web channel gains WebSocket or SSE push support.
        """
        pass

    async def send_notification(self, doctor_id: str, notification: str) -> None:
        """Deferred — not wired into production.

        Web notifications are currently polled by the client.  This stub
        exists to satisfy the ``ChannelAdapter`` protocol and will be
        implemented when a server-push notification channel (WebSocket,
        SSE, or polling endpoint) is added to the web frontend.
        """
        pass

    async def get_history(self, doctor_id: str) -> List[dict]:
        """Web history is extracted from the request body, not stored here."""
        return []
