"""
规则驱动的任务自动生成。

扫描病历文本中的关键词，自动创建对应类型的随访任务，无需 LLM。
在 save_pending_record 确认后调用，与 create_follow_up_task (LLM解析 follow_up_plan) 互补：
- follow_up_plan 控制「几天/周/月后随访」
- task_rules 控制「化验复核/转诊/影像复查/用药提醒」等专项任务

支持任务类型：
  lab_review   — 化验单/检验结果复核（默认 5 天后）
  referral     — 转诊安排（次日）
  imaging      — 影像复查（7 天后）
  medication   — 用药/服药提醒（1 天后）
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

@dataclass
class _TaskRule:
    task_type: str
    title_template: str   # {patient_name} placeholder
    default_days: int     # due offset from now
    keywords: frozenset[str]
    # Optional: keyword that BLOCKS this rule when present in text
    suppressed_by: frozenset[str] = frozenset()


_RULES: List[_TaskRule] = [
    _TaskRule(
        task_type="lab_review",
        title_template="检验结果复核：{patient_name}",
        default_days=5,
        keywords=frozenset({
            "化验单", "检验单", "抽血", "查血", "验血",
            "等待结果", "等检验", "待报告", "化验结果",
            "血常规", "生化全套", "凝血", "尿常规", "大便常规",
            "HbA1c", "hba1c", "肝功", "肾功", "甲功",
            "BNP", "bnp", "CRP", "crp", "PCT", "pct",
        }),
        suppressed_by=frozenset({"结果已回", "结果正常", "结果出来了"}),
    ),
    _TaskRule(
        task_type="referral",
        title_template="转诊跟进：{patient_name}",
        default_days=1,
        keywords=frozenset({
            "转诊", "会诊", "转上级", "转院", "请外科", "请内科",
            "请专科", "请神经科", "请心内科", "请骨科", "请眼科",
            "建议转", "转至", "介绍信",
        }),
        suppressed_by=frozenset({"已转诊", "转诊完成"}),
    ),
    _TaskRule(
        task_type="imaging",
        title_template="影像复查：{patient_name}",
        default_days=7,
        keywords=frozenset({
            "CT复查", "MRI复查", "X光复查", "超声复查", "B超复查",
            "复查CT", "复查MRI", "复查X光", "复查超声", "复查B超",
            "复查心脏彩超", "复查胸片", "复查心电图", "复查ECG",
            "待影像", "待CT", "待MRI",
        }),
        suppressed_by=frozenset({"影像已复查", "复查完成"}),
    ),
    _TaskRule(
        task_type="medication",
        title_template="用药提醒：{patient_name}",
        default_days=1,
        keywords=frozenset({
            "每日服药", "按时服药", "规律服药",
            "qd", "bid", "tid", "qid",   # dosing frequencies
            "早晚各", "每天两次", "每天三次",
            "新开药", "换药", "调整用药", "加量", "减量",
            "首次用药", "初始剂量",
        }),
        suppressed_by=frozenset({"已告知用药", "用药依从"}),
    ),
]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

@dataclass
class AutoTaskSpec:
    """Specification for a task to be auto-created from record text."""
    task_type: str
    title: str
    content: str    # brief reason shown in task content
    due_days: int   # from now


def detect_auto_tasks(text: str, patient_name: str) -> List[AutoTaskSpec]:
    """
    Scan record text and return a list of AutoTaskSpec for tasks that should
    be auto-created.  Each rule fires at most once per call.

    Args:
        text: the clinical note content
        patient_name: used in task titles

    Returns:
        List of AutoTaskSpec, possibly empty.
    """
    if not text:
        return []

    text_lower = text.lower()
    specs: List[AutoTaskSpec] = []

    for rule in _RULES:
        # Check suppression first
        if any(sup in text for sup in rule.suppressed_by):
            continue
        # Check if any keyword matches
        triggered_kw: Optional[str] = None
        for kw in rule.keywords:
            if kw.lower() in text_lower:
                triggered_kw = kw
                break
        if triggered_kw is None:
            continue

        specs.append(AutoTaskSpec(
            task_type=rule.task_type,
            title=rule.title_template.format(patient_name=patient_name),
            content=f"触发关键词：「{triggered_kw}」",
            due_days=rule.default_days,
        ))

    return specs


# ---------------------------------------------------------------------------
# Due-date override: extract more specific timing from text
# ---------------------------------------------------------------------------

_DUE_OVERRIDE_RE = re.compile(
    r"([一两二三四五六七八九十\d]+)\s*(?:天|日)后"
    r"|([一两二三四五六七八九十\d]+)\s*周后"
    r"|([一两二三四五六七八九十\d]+)\s*个月后"
    r"|(下周|下个周)"         # → 7 days
    r"|(下个月|下月)"         # → 30 days
)

_CN_MAP = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _cn_or_int(s: str) -> int:
    return _CN_MAP.get(s) or int(s)


def refine_due_days(text: str, default_days: int) -> int:
    """
    If the record mentions a concrete time window near a lab/imaging keyword,
    use that instead of the rule's default.  E.g. "5天后复查CT" → 5 days.
    """
    m = _DUE_OVERRIDE_RE.search(text)
    if not m:
        return default_days
    try:
        if m.group(1):
            return _cn_or_int(m.group(1))
        if m.group(2):
            return _cn_or_int(m.group(2)) * 7
        if m.group(3):
            return _cn_or_int(m.group(3)) * 30
        if m.group(4):   # 下周
            return 7
        if m.group(5):   # 下个月
            return 30
    except (ValueError, KeyError):
        pass
    return default_days
