"""Shared compound-turn normalizer — residual-text clinical content detection,
same-turn correction detection, and secondary-intent signal helpers.

Replaces the brittle ``CLINICAL_CONTENT_HINTS`` keyword list with a general
residual-text approach that works across all specialties.  Used by the entity
extraction layer and the planner's unsupported-combo gate.
"""

from __future__ import annotations

import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.ai.intent import IntentResult

from services.domain.text_cleanup import strip_leading_create_demographics

# ---------------------------------------------------------------------------
# Residual-text clinical content detection
# ---------------------------------------------------------------------------

# Minimum meaningful residual: 4+ mixed CJK/digit/alpha chars, or 2+ ASCII
# letters (medical abbreviation like EF, BNP, ST).  Filters greetings (你好)
# and bare commands while passing minimal clinical phrases.
_MEANINGFUL_TEXT_RE = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{4}"  # 4+ mixed chars (CJK + alphanumeric)
    r"|[A-Z]{2}"                      # 2+ uppercase ASCII (EF, ST, BNP, HER2)
)


def has_residual_clinical_content(
    text: str,
    intent_result: Optional["IntentResult"] = None,
    *,
    patient_name: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
) -> tuple[bool, str]:
    """Check if *text* has meaningful clinical content after stripping demographics.

    Returns ``(has_content, residual_text)``.

    Replaces the fixed ``CLINICAL_CONTENT_HINTS`` keyword list with a general
    residual-text approach that works across all medical specialties.
    """
    residual = strip_leading_create_demographics(
        text, intent_result,
        patient_name=patient_name, gender=gender, age=age,
    )
    has_content = bool(_MEANINGFUL_TEXT_RE.search(residual))
    return has_content, residual


# ---------------------------------------------------------------------------
# Same-turn correction detection
# ---------------------------------------------------------------------------

_CORRECTION_RE = re.compile(
    r"(?:说错了|写错了|搞错了|不对[，,]|改为|改成|更正为|纠正|更正|应该是)"
)


def detect_same_turn_correction(text: str) -> bool:
    """Detect same-turn correction language in the text.

    When detected inside a create/add-record turn, the correction rewrites the
    unsaved payload rather than spawning a separate ``update_record`` action.
    """
    return bool(_CORRECTION_RE.search(text or ""))


# ---------------------------------------------------------------------------
# Clinical location context (shared by gate.py and _add_record.py)
# ---------------------------------------------------------------------------

LOCATION_CONTEXT_RE = re.compile(
    r"(?:ICU|PACU|CCU|NICU|急诊|抢救室|手术室|监护室|留观|绿色通道"
    r"|\d+床|\d+号床|[A-Z]?\d+病房|[A-Z]?\d+号)",
    re.IGNORECASE,
)


def has_clinical_location_context(text: str) -> bool:
    """Return True if text contains explicit clinical location markers."""
    return bool(LOCATION_CONTEXT_RE.search(text or ""))


# ---------------------------------------------------------------------------
# Secondary-intent signal patterns (used by the planner)
# ---------------------------------------------------------------------------

WRITE_VERB_RE = re.compile(r"(?:录入|创建|新建|建立|添加)")
QUERY_VERB_RE = re.compile(r"(?:查询|查看|查一下|看一下|看看)")
DESTRUCTIVE_VERB_RE = re.compile(r"(?:删除|删掉|移除|清空)")
UPDATE_VERB_RE = re.compile(r"(?:修改|更新|上一条有误|刚才写错)")

# Conjunction patterns that strongly suggest multi-clause turns.
# Require a separator (comma / semicolon / period) before the conjunction
# to reduce false-positives in clinical narratives like "胸痛然后做了PCI".
CONJUNCTION_RE = re.compile(
    r"[，,。；;]\s*(?:然后|再|同时|并且|接着|另外|顺便|还要)"
)
