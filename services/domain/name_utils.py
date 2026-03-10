"""
患者姓名解析工具：从文本和对话历史中提取、验证患者姓名。
"""

from __future__ import annotations

import re
from typing import List, Optional


# Phrases that indicate the LLM accidentally extracted a question/non-name as a patient name
_BAD_NAME_FRAGMENTS = [
    "叫什么名字", "这位患者", "请问", "患者姓名",
    # Clinical action phrases wrongly extracted as names
    "入院前", "入院体征", "入院查", "入院后",
    "补一条", "补病程", "补病历", "补全", "补记录",
    "急查", "查体", "急诊",
]
# Structural patterns that are never valid patient names
_BAD_NAME_RE = re.compile(
    r"^[0-9一二三四五六七八九十百]+床$"    # bed numbers: "3床", "第七床"
    r"|^第[一二三四五六七八九十]+床$"       # "第三床"
    r"|^[0-9]+[MF]$"                        # demographic codes: "62M", "53F"
    r"|^[男女][，,\s]*[0-9]+岁$"            # "女65岁", "男，42岁"
    r"|^[0-9]+[，,\s]*[男女]$"              # "65，女"
)
_NAME_ONLY = re.compile(r"^[\u4e00-\u9fff]{2,4}$")
_ASK_NAME_FRAGMENTS = ("叫什么名字", "患者姓名", "请提供姓名", "请告知姓名")
_LEADING_NAME = re.compile(r"^\s*([\u4e00-\u9fff]{2,4})(?:[，,\s]|$)")
_CLINICAL_HINTS = (
    "男", "女", "岁", "胸痛", "胸闷", "心悸", "头痛", "发热", "咳嗽",
    "ST", "PCI", "BNP", "EF", "诊断", "治疗", "复查",
)

# Patterns to extract patient name from assistant history messages.
_HISTORY_PATIENT_BRACKET_RE = re.compile(r"【([\u4e00-\u9fff]{2,4})】")
_HISTORY_PATIENT_ARCHIVE_RE = re.compile(r"([\u4e00-\u9fff]{2,4})的(?:档案|病历)")

# Extract patient name from doctor/user turns.
_HISTORY_DOCTOR_TURN_RE = re.compile(
    r"(?:^|[。！\n])\s*(?:把|将|找到?|看[看下]?|查|调出?|给)\s*([\u4e00-\u9fff]{2,3})"
    r"(?=[，,的今昨\s]|的['\u201c「]|$)"
    r"|"
    r"^([\u4e00-\u9fff]{2,3})的(?:['\u201c「]|(?:任务|记录|手术|评估|化疗|随访|透析|指标))"
    r"|"
    r"([\u4e00-\u9fff]{2,3})(?:今天|全年|20\d\d年)"
)


def is_valid_patient_name(name: str) -> bool:
    """Return False if the extracted name is clearly not a real patient name."""
    if not name or not name.strip():
        return False
    n = name.strip()
    if len(n) > 20:
        return False
    if any(frag in n for frag in _BAD_NAME_FRAGMENTS):
        return False
    if _BAD_NAME_RE.match(n):
        return False
    return True


def assistant_asked_for_name(history: List[dict]) -> bool:
    """True when the most recent assistant message asks for patient name."""
    if not history:
        return False
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        content = (message.get("content") or "").strip()
        return any(fragment in content for fragment in _ASK_NAME_FRAGMENTS)
    return False


def last_assistant_was_unclear_menu(history: List[dict]) -> bool:
    """True when the most recent assistant message is the unclear-intent numbered menu."""
    for message in reversed(history):
        if message.get("role") != "assistant":
            continue
        content = (message.get("content") or "").strip()
        return content.startswith("我还不能确定您的操作意图")
    return False


def name_only_text(text: str) -> Optional[str]:
    """Return Chinese name for a name-only message, else None."""
    candidate = text.strip()
    if not _NAME_ONLY.match(candidate):
        return None
    if not is_valid_patient_name(candidate):
        return None
    return candidate


def leading_name_with_clinical_context(text: str) -> Optional[str]:
    """Extract leading name from clinical dictation like '张三，男，52岁，胸闷'."""
    candidate_match = _LEADING_NAME.match(text or "")
    if not candidate_match:
        return None
    candidate = candidate_match.group(1).strip()
    if not is_valid_patient_name(candidate):
        return None
    remainder = (text or "").strip()[len(candidate):]
    if not any(hint in remainder for hint in _CLINICAL_HINTS):
        return None
    return candidate


def patient_name_from_history(history: List[dict]) -> Optional[str]:
    """Scan recent conversation history for the most recently mentioned patient name.

    Checks assistant turns for 【NAME】 bracket / NAME的档案 patterns.
    Also checks doctor/user turns for names appearing before task/time markers.
    Returns the first (most recent) valid patient name found, or None.
    """
    for msg in reversed(history[-8:]):
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "assistant":
            for pattern in (_HISTORY_PATIENT_BRACKET_RE, _HISTORY_PATIENT_ARCHIVE_RE):
                m = pattern.search(content)
                if m:
                    name = m.group(1)
                    if is_valid_patient_name(name):
                        return name
        elif role == "user":
            for m in _HISTORY_DOCTOR_TURN_RE.finditer(content):
                for g in (1, 2, 3):
                    try:
                        name = m.group(g)
                    except IndexError:
                        continue
                    if name and is_valid_patient_name(name):
                        return name
    return None
