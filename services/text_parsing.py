from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Token / name validation helpers
# ---------------------------------------------------------------------------

_NAME_TOKEN_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
_NON_NAME_TOKENS = {"你好", "您好", "谢谢", "好的", "收到", "在吗", "哈喽", "嗯", "嗯嗯"}
_NON_NAME_SUBSTRINGS = {
    "发烧", "咳嗽", "头痛", "胸闷", "疼", "痛", "不适", "心悸", "气短",
    "一天", "两天", "三天", "一周", "两周", "三周", "一月", "两月",
    "记录", "病历", "查询", "随访", "复查", "预约",
}
_SYMPTOM_KEYWORDS = (
    "头疼", "头痛", "偏头痛", "发烧", "咳嗽", "胸闷", "胸痛",
    "腹痛", "恶心", "呕吐", "腹泻", "乏力", "眩晕", "心悸",
    "不舒服", "不适", "难受", "疼",
)
_EXPLICIT_NAME_PATTERNS = [
    re.compile(r"^\s*我是(?P<name>[\u4e00-\u9fff]{2,4})\s*$"),
    re.compile(r"^\s*我叫(?P<name>[\u4e00-\u9fff]{2,4})\s*$"),
    re.compile(r"^\s*患者(?:是|叫)?(?P<name>[\u4e00-\u9fff]{2,4})\s*$"),
]


def name_token_or_none(text: str) -> str:
    """Return *text* if it looks like a bare patient name, else empty string."""
    candidate = text.strip()
    if _NAME_TOKEN_RE.match(candidate) and candidate not in _NON_NAME_TOKENS:
        if any(x in candidate for x in _NON_NAME_SUBSTRINGS):
            return ""
        return candidate
    return ""


def explicit_name_or_none(text: str) -> str:
    """Return a patient name if *text* matches an explicit name-statement pattern."""
    for pat in _EXPLICIT_NAME_PATTERNS:
        m = pat.match(text.strip())
        if not m:
            continue
        name = m.group("name")
        return name_token_or_none(name)
    return ""


def looks_like_symptom_note(text: str) -> bool:
    """Return True when *text* is a short symptom description (≤30 chars)."""
    s = text.strip()
    if not s:
        return False
    if len(s) > 30:
        return False
    return any(k in s for k in _SYMPTOM_KEYWORDS)
