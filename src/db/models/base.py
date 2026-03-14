"""
数据库模型基础工具：提供统一的 UTC 时间戳辅助函数。
"""

from __future__ import annotations

from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
