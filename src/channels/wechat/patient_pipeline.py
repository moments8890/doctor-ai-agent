"""Patient-facing WeChat message utilities: emergency keyword detection.

The actual patient message handling now goes through the ReAct agent
via ``handle_turn(text, "patient", open_id)`` in the WeChat router.
This module retains emergency detection and static reply constants
used by the router and KF handlers.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Emergency detection
# ---------------------------------------------------------------------------

_EMERGENCY_KEYWORDS = frozenset(
    {
        "胸痛", "胸闷", "心梗", "心脏骤停", "心脏病发", "中风", "脑卒中",
        "呼吸困难", "喘不过气", "晕倒", "意识丧失", "意识不清", "昏迷",
        "大出血", "严重出血", "骨折", "溺水", "触电", "急救", "救命",
        "休克", "脑出血", "急性腹痛",
    }
)

_EMERGENCY_REPLY = (
    "⚠️ 您描述的症状可能是急症，请立即拨打 120 急救电话！\n\n"
    "等待救护车期间：\n"
    "- 保持冷静，不要独自行动\n"
    "- 告知家人或周围人\n"
    "- 如有需要，可拨打 110 或 119 配合救援"
)

_NON_TEXT_REPLY = (
    "您好！\n"
    "此频道目前支持文字消息。\n"
    "如需就医咨询，请直接发送文字提问；\n"
    "如有紧急情况，请拨打 120。"
)


def has_emergency_keyword(text: str) -> bool:
    """Return True if text contains any emergency keyword."""
    return any(kw in text for kw in _EMERGENCY_KEYWORDS)
