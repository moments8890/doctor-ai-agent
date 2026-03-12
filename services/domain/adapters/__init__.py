"""Channel adapter implementations."""

from __future__ import annotations

from .web_adapter import WebAdapter
from .wechat_adapter import WeChatAdapter

__all__ = ["WebAdapter", "WeChatAdapter"]
