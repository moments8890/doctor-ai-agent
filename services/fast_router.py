"""
Tiered intent routing without LLM — serves predictable doctor commands in <1ms.

Tier 1: Exact keyword match  (list patients, list tasks)
Tier 2: Regex pattern match   (query records, create patient, delete patient,
                               complete task)

Returns None when uncertain so the caller can fall through to LLM dispatch.
Target: 30%+ of turns resolved here at ~0ms vs. ~6s LLM baseline.
"""

from __future__ import annotations

import re
from typing import Optional

from services.intent import Intent, IntentResult

# ── Text normalisation ─────────────────────────────────────────────────────────
# Strip leading polite particles and trailing punctuation.
# Internal punctuation is intentionally preserved to avoid merging adjacent words.
_LEAD_FILLER_RE = re.compile(r"^(?:帮我|帮|请|麻烦|给我|给|我要|我想|可以)[\s　]*")
_TRAIL_PUNCT_RE = re.compile(r"[\s　。？！，、…]+$")

def _normalise(text: str) -> str:
    """Strip leading polite particles and trailing punctuation."""
    t = _LEAD_FILLER_RE.sub("", text.strip())
    return _TRAIL_PUNCT_RE.sub("", t)


# ── Tier 1: Exact / normalised keyword sets ────────────────────────────────────

_LIST_PATIENTS_EXACT: frozenset[str] = frozenset(
    {
        "患者列表", "所有患者", "全部患者", "患者名单", "病人列表",
        "病人名单", "我的患者", "我的病人", "列出患者", "列出病人",
        "看看患者", "查看患者", "患者信息", "显示患者", "所有病人",
        "有哪些患者", "有哪些病人", "患者都有谁", "病人都有谁",
        "列出所有患者", "列出所有病人",
    }
)
# Very short triggers — only match if the entire message is exactly these chars
_LIST_PATIENTS_SHORT: frozenset[str] = frozenset({"患者", "病人"})

_LIST_TASKS_EXACT: frozenset[str] = frozenset(
    {
        "待办任务", "任务列表", "我的任务", "查看任务", "待处理",
        "待办事项", "有什么任务", "有啥任务", "待处理任务",
        "查看待办", "显示任务", "显示待办", "有哪些任务",
        "最近任务", "今天任务", "所有任务",
    }
)
_LIST_TASKS_SHORT: frozenset[str] = frozenset({"待办", "任务"})

# ── Domain keywords that must never be treated as patient names ────────────────
_NON_NAME_KEYWORDS: frozenset[str] = frozenset({
    "病历", "记录", "情况", "病情", "近况", "状态",
    "任务", "待办", "患者", "病人", "诊断", "治疗",
})

# ── Chinese name pattern ───────────────────────────────────────────────────────
# Names: 2-3 chars (most Chinese names); 4-char names are rare and we avoid
# greedily consuming keywords that follow.
_NAME_PAT = r"([\u4e00-\u9fff]{2,3})"

# Record-domain keywords that follow a name (not part of the name)
_RECORD_KW = r"(?:病历|记录|情况|病情|近况|状态)"

# ── Tier 2: Regex patterns ─────────────────────────────────────────────────────

# Query: 查/查询/查看/查一下/帮我查/看一下 [name] + optional trailing keyword
# Use non-greedy name so "看一下王五的情况" doesn't capture "的" as part of name.
_QUERY_PREFIX_RE = re.compile(
    r"^(?:帮我查|查询|查看|查一下|看一下|查)\s*([\u4e00-\u9fff]{2,3}?)\s*(?:的)?" + _RECORD_KW + r"?$"
)

# Query: [name] + 的 + record keyword  (optional trailing question particle)
_QUERY_SUFFIX_RE = re.compile(
    r"^" + _NAME_PAT + r"\s*的\s*" + _RECORD_KW + r"(?:怎么样|如何|什么)?$"
)

# Query: [name] immediately followed by record keyword (no 的)
_QUERY_NAME_QUESTION_RE = re.compile(
    r"^" + _NAME_PAT + r"\s*" + _RECORD_KW + r"$"
)

# Create: leading keyword directly before the name.
# Longer alternatives listed first so Python re tries them left-to-right.
_CREATE_LEAD_RE = re.compile(
    r"(?:"
    r"帮我建个新患者|帮我建个新病人|帮我加个患者|帮我加个病人"
    r"|建个新患者|建个新病人"
    r"|新建患者|新建病人"
    r"|添加患者|添加病人"
    r"|加个患者|加个病人"
    r"|录入患者|录入病人"
    r"|新患者|新病人"
    r"|建档"
    r")"
    r"[\s,，]*" + _NAME_PAT
)

# Create: "[name] + trailing keyword"
_CREATE_TRAIL_RE = re.compile(
    _NAME_PAT + r"\s*(?:新患者|新病人|建档|建个档)"
)

# Demographics helpers
_GENDER_RE = re.compile(r"[男女](?:性)?")
_AGE_RE = re.compile(r"(\d{1,3})\s*岁")

# Delete leading: "删除/删掉/移除 [患者/病人] [name]"
_DELETE_LEAD_RE = re.compile(
    r"^(?:删除|删掉|移除|删)(?:患者|病人)?\s*" + _NAME_PAT + r"\s*$"
)

# Delete trailing: "把[name]删了/删掉" or "[name]删除/删掉"
_DELETE_TRAIL_RE = re.compile(
    r"^(?:把\s*)?" + _NAME_PAT + r"\s*(?:删了|删掉|删除|移除)\s*$"
)

# Complete task: "完成任务N", "完成N", "标记N完成", "任务N完成", "N完成"
# N may be Arabic digits or Chinese ordinals.
# Split into three separate patterns to avoid duplicate named-group error.
_CN_DIGIT = r"[一二三四五六七八九十百]+"
_TASK_NUM = r"(\d+|" + _CN_DIGIT + r")"
_DONE_WORDS = r"(?:完成|搞定|已完成|做好了|做完了)"
# Pattern A: "完成/搞定/标记完成 [任务] N"
_COMPLETE_TASK_A_RE = re.compile(
    r"^(?:完成|搞定|标记完成)\s*(?:任务|待办)?\s*" + _TASK_NUM + r"\s*$"
)
# Pattern B: "[任务/待办] N + done-word"
_COMPLETE_TASK_B_RE = re.compile(
    r"^(?:任务|待办)\s*" + _TASK_NUM + r"\s*" + _DONE_WORDS + r"\s*$"
)
# Pattern C: "N + done-word" (bare number)
_COMPLETE_TASK_C_RE = re.compile(
    r"^" + _TASK_NUM + r"\s*" + _DONE_WORDS + r"\s*$"
)
_CN_NUM_MAP = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
}


def _parse_task_num(raw: str) -> Optional[int]:
    if raw.isdigit():
        return int(raw)
    return _CN_NUM_MAP.get(raw)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_demographics(text: str) -> tuple[Optional[str], Optional[int]]:
    """Extract gender and age from a message fragment."""
    gm = _GENDER_RE.search(text)
    gender: Optional[str] = gm.group(0)[0] if gm else None  # just 男/女
    am = _AGE_RE.search(text)
    age: Optional[int] = int(am.group(1)) if am else None
    return gender, age


# ── Public API ─────────────────────────────────────────────────────────────────

def fast_route(text: str) -> Optional[IntentResult]:
    """
    Attempt to resolve intent without LLM.

    Returns IntentResult on high-confidence match, None if uncertain (LLM fallback).
    All matches are intentionally conservative — a false negative (LLM handles it) is
    always safer than a false positive (wrong intent served without LLM confirmation).
    """
    stripped = text.strip()
    if not stripped:
        return None

    # Normalised form used for Tier 1 set lookups (strips polite particles etc.)
    normed = _normalise(stripped)

    # ── Tier 1: list_patients ──────────────────────────────────────────────────
    if normed in _LIST_PATIENTS_EXACT or stripped in _LIST_PATIENTS_EXACT:
        return IntentResult(intent=Intent.list_patients)
    if normed in _LIST_PATIENTS_SHORT or stripped in _LIST_PATIENTS_SHORT:
        return IntentResult(intent=Intent.list_patients)

    # ── Tier 1: list_tasks ────────────────────────────────────────────────────
    if normed in _LIST_TASKS_EXACT or stripped in _LIST_TASKS_EXACT:
        return IntentResult(intent=Intent.list_tasks)
    if normed in _LIST_TASKS_SHORT or stripped in _LIST_TASKS_SHORT:
        return IntentResult(intent=Intent.list_tasks)

    # ── Tier 2: complete_task (fully deterministic — no LLM needed) ───────────
    for _pat in (_COMPLETE_TASK_A_RE, _COMPLETE_TASK_B_RE, _COMPLETE_TASK_C_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            task_id = _parse_task_num(m.group(1))
            return IntentResult(
                intent=Intent.complete_task,
                extra_data={"task_id": task_id},
            )

    # ── Tier 2: query_records ─────────────────────────────────────────────────
    for target in (normed, stripped):
        m = _QUERY_PREFIX_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.query_records, patient_name=m.group(1))

        m = _QUERY_SUFFIX_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.query_records, patient_name=m.group(1))

        m = _QUERY_NAME_QUESTION_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.query_records, patient_name=m.group(1))

    # ── Tier 2: create_patient ────────────────────────────────────────────────
    for target in (normed, stripped):
        m = _CREATE_LEAD_RE.search(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            name = m.group(1)
            gender, age = _extract_demographics(stripped)
            return IntentResult(
                intent=Intent.create_patient,
                patient_name=name,
                gender=gender,
                age=age,
            )

        m = _CREATE_TRAIL_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            name = m.group(1)
            gender, age = _extract_demographics(stripped)
            return IntentResult(
                intent=Intent.create_patient,
                patient_name=name,
                gender=gender,
                age=age,
            )

    # ── Tier 2: delete_patient ────────────────────────────────────────────────
    for target in (normed, stripped):
        m = _DELETE_LEAD_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.delete_patient, patient_name=m.group(1))

        m = _DELETE_TRAIL_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            return IntentResult(intent=Intent.delete_patient, patient_name=m.group(1))

    return None


def fast_route_label(text: str) -> str:
    """Return a routing label and record it in routing_metrics."""
    result = fast_route(text)
    label = "llm" if result is None else f"fast:{result.intent.value}"
    from services.routing_metrics import record
    record(label)
    return label
