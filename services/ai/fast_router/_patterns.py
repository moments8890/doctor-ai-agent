"""
快速路由正则模式库：编译后的正则表达式和纯辅助函数，无包内依赖。

Pattern groups follow the execution order of _route_tier2_all() in _router.py:
  task_actions → followup → appointment → export → query → create → delete → update
"""

from __future__ import annotations

import re
from typing import Optional

# ── Text normalisation ─────────────────────────────────────────────────────────
# Strip leading polite particles and trailing punctuation.
# Internal punctuation is intentionally preserved to avoid merging adjacent words.
_LEAD_FILLER_RE = re.compile(r"^(?:帮我|帮|请|麻烦|给我|给|我要|我想|可以)[\s　]*")
_TRAIL_PUNCT_RE = re.compile(r"[\s　。？！，、…]+$")


def _normalise(text: str) -> str:
    """Strip leading polite particles and trailing punctuation."""
    t = _LEAD_FILLER_RE.sub("", text.strip())
    return _TRAIL_PUNCT_RE.sub("", t)


# ── Tier 1: Flex patterns ──────────────────────────────────────────────────────
_LIST_TASKS_FLEX_RE = re.compile(
    r"^(?:先|再)?(?:看下|看一下|查看|查一下)\s*(?:我?(?:还有|今天有?|最近|今天的?)?(?:几个|哪些|什么)?\s*)"
    r"(?:待办|任务)(?:吗|呢|？)?$"
)
_LIST_PATIENTS_FLEX_RE = re.compile(
    r"^(?:再|先)?(?:给我|帮我看|看一下)?\s*(?:所有|全部|所有的|全部的)?\s*(?:患者|病人)(?:列表|名单|信息)?$"
)

# ══════════════════════════════════════════════════════════════════════════════
# Shared building blocks
# ══════════════════════════════════════════════════════════════════════════════

# Chinese name: 2-3 chars (greedy). 4-char variant for delete (compound surnames).
_NAME_PAT = r"([\u4e00-\u9fff]{2,3})"
_NAME_PAT_4 = r"([\u4e00-\u9fff]{2,4})"
_LAZY_NAME_PAT = r"([\u4e00-\u9fff]{2,3}?)"

# Record-domain keywords that follow a name (not part of the name).
# Only high-confidence nouns kept.  Broader terms (情况, 近况, 状态) are
# semantically ambiguous and deferred to the routing LLM.
_RECORD_KW = r"(?:病历|记录|病情)"

# Numerals and time units (shared by follow-up, task, postpone patterns)
_CN_NUM = r"[一两二三四五六七八九十\d]+"
_CN_DIGIT = r"[一二三四五六七八九十百]+"
_CN_NUM_MAP = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
}
_TIME_UNIT = r"(?:天|日|周|个月|月)"
# Concrete relative dates only; vague tokens (下次, 近期) deferred to LLM.
_RELATIVE_TIME = r"(?:下周|下个月|明天|后天)"
_FOLLOW_UP_KW = r"(?:随访|复诊|复查|随诊|随访提醒|复查提醒)"
_TASK_NUM = r"(\d+|" + _CN_DIGIT + r")"
_DONE_WORDS = r"(?:完成|搞定|已完成|做好了|做完了)"

# Demographics helpers
_GENDER_RE = re.compile(r"[男女](?:性)?")
_AGE_RE = re.compile(r"(\d{1,3})\s*岁")

# Guard: destructive verb in mixed commands (e.g. "删除张三，再创建李四")
_CONFLICTING_PREFIX_RE = re.compile(
    r"(?:删除|删掉|移除|删|取消|撤销|清空|作废)"
)


def _cn_or_arabic(s: str) -> int:
    """Parse a Chinese or Arabic numeral string."""
    if s.isdigit():
        return int(s)
    v = _CN_NUM_MAP.get(s)
    if v is None:
        raise ValueError(f"unrecognised number token: {s!r}")
    return v


def _time_unit_to_days(n_str: str, unit: str) -> int:
    n = _cn_or_arabic(n_str)
    if "月" in unit:
        return n * 30
    if "周" in unit:
        return n * 7
    return n  # 天/日


def _parse_task_num(raw: str) -> Optional[int]:
    if raw.isdigit():
        return int(raw)
    return _CN_NUM_MAP.get(raw)


def _extract_demographics(text: str) -> tuple[Optional[str], Optional[int]]:
    """Extract gender and age from a message fragment."""
    gm = _GENDER_RE.search(text)
    gender: Optional[str] = gm.group(0)[0] if gm else None  # just 男/女
    am = _AGE_RE.search(text)
    age: Optional[int] = int(am.group(1)) if am else None
    return gender, age


# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Task actions: complete / cancel / postpone
# ══════════════════════════════════════════════════════════════════════════════

# complete_task: "完成任务3", "任务2搞定", "把第3条标记完成"
_COMPLETE_TASK_A_RE = re.compile(
    r"^(?:完成|搞定|标记完成)\s*(?:任务|待办)?\s*" + _TASK_NUM + r"\s*$"
)
_COMPLETE_TASK_B_RE = re.compile(
    r"^(?:任务|待办)\s*" + _TASK_NUM + r"\s*" + _DONE_WORDS + r"\s*$"
)
_COMPLETE_TASK_C_RE = re.compile(
    r"^" + _TASK_NUM + r"\s*" + _DONE_WORDS + r"\s*$"
)
_COMPLETE_TASK_D_RE = re.compile(
    r"^把第\s*" + _TASK_NUM + r"\s*条(?:\s*标记)?\s*" + _DONE_WORDS + r"[。！]?\s*$"
)

# cancel_task: "取消任务3", "任务2取消", "取消第3个任务"
_CANCEL_TASK_A_RE = re.compile(r"^取消任务([一两二三四五六七八九十\d]+)$")
_CANCEL_TASK_B_RE = re.compile(r"^任务([一两二三四五六七八九十\d]+)取消$")
_CANCEL_TASK_C_RE = re.compile(r"^取消第([一两二三四五六七八九十\d]+)(?:个|条)?任务$")

# postpone_task: "推迟任务3一周", "任务2延后3天"
_POSTPONE_TASK_RE = re.compile(
    r"^(?:推迟|延迟|推后|延后)\s*任务\s*([一两二三四五六七八九十\d]+)\s*"
    r"(" + _CN_NUM + r")\s*(" + _TIME_UNIT + r")$"
)
_POSTPONE_TASK_B_RE = re.compile(
    r"^任务\s*([一两二三四五六七八九十\d]+)\s*(?:推迟|延迟|推后|延后)\s*"
    r"(" + _CN_NUM + r")\s*(" + _TIME_UNIT + r")$"
)

# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Follow-up scheduling
# ══════════════════════════════════════════════════════════════════════════════

# With patient name: "给张三设3个月后随访提醒", "张三3个月后复诊"
# Time clause is REQUIRED — bare "张三复查" is too ambiguous for fast path.
_FOLLOWUP_WITH_TIME_RE = re.compile(
    r"^(?:给|为)?\s*" + _LAZY_NAME_PAT + r"\s*"
    r"(?:设|安排|创建|建|定)?\s*"
    r"(" + _CN_NUM + r")\s*(" + _TIME_UNIT + r")后\s*"
    + _FOLLOW_UP_KW + r"(?:提醒)?$"
)
_FOLLOWUP_RELATIVE_RE = re.compile(
    r"^(?:给|为)?\s*" + _LAZY_NAME_PAT + r"\s*"
    r"(?:设|安排|创建|建|定)?\s*"
    r"(" + _RELATIVE_TIME + r")\s*"
    + _FOLLOW_UP_KW + r"(?:提醒)?$"
)
_FOLLOWUP_TIME_FIRST_RE = re.compile(
    r"^(" + _CN_NUM + r")\s*(" + _TIME_UNIT + r")后\s*" + _FOLLOW_UP_KW + r"\s*"
    + _LAZY_NAME_PAT + r"$"
)

# Nameless follow-up patterns removed — they rely on session context (semantic,
# not deterministic).  Deferred to LLM for proper patient resolution.

# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Appointment scheduling
# ══════════════════════════════════════════════════════════════════════════════

_DATE_TIME_PAT = (
    r"(?:"
    r"\d+月\d+[日号]"          # 3月15日
    r"|下周[一二三四五六七日]?"  # 下周三
    r"|" + _RELATIVE_TIME +
    r")"
    r"(?:\s*\d{1,2}[点时:：]\d{0,2})?"  # optional hour
)
# Time is required: "给张三预约" without a date is too ambiguous.
_APPOINTMENT_RE = re.compile(
    r"^(?:给|为|帮|替)?\s*" + _LAZY_NAME_PAT + r"\s*"
    r"(?:预约|约诊|挂号|安排(?:复诊|门诊|预约))\s*"
    r"(?:" + _DATE_TIME_PAT + r")\s*$"
)
_APPOINTMENT_VERB_FIRST_RE = re.compile(
    r"^(?:预约|约)\s*" + _LAZY_NAME_PAT + r"\s*"
    r"(?:" + _DATE_TIME_PAT + r")\s*$"
)

# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Export / outpatient report
# ══════════════════════════════════════════════════════════════════════════════

# Export: 导出/打印/下载 [name] 的病历/记录/报告
_EXPORT_RE = re.compile(
    r"^(?:帮我)?(?:导出|打印|下载|生成)\s*(?!病历|记录|报告|医疗记录)([\u4e00-\u9fff]{2,4}?)\s*(?:的)?\s*(?:病历|记录|报告|医疗记录)?(?:pdf|PDF)?$"
)
# Nameless export: requires explicit export verb + report noun.
# Semantic cues (会诊用, MDT用, 需要病历文件) removed — deferred to LLM.
_EXPORT_NONAME_RE = re.compile(
    r"^(?:帮我)?(?:导出|打印|下载|生成)\s*(?:(?:目前|当前|这个|这位|患者)的?)?\s*(?:病历|记录|报告|医疗记录)(?:pdf|PDF)?$"
)

# Outpatient report (卫生部 2010 门诊病历 standard format)
_OUTPATIENT_REPORT_RE = re.compile(
    r"^(?:帮我)?(?:生成|导出|打印|下载)\s*(?!标准门诊病历|门诊病历|卫生部病历|正式病历|标准病历)([\u4e00-\u9fff]{2,4}?)\s*(?:的)?\s*"
    r"(?:标准门诊病历|门诊病历|卫生部病历|正式病历|标准病历)(?:pdf|PDF)?$"
)
_OUTPATIENT_REPORT_NONAME_RE = re.compile(
    r"^(?:帮我)?(?:生成|导出|打印|下载)\s*(?:(?:目前|当前|这个|这位|患者)的?)?\s*"
    r"(?:标准门诊病历|门诊病历|卫生部病历|正式病历|标准病历)(?:pdf|PDF)?$"
)

# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Query records
# ══════════════════════════════════════════════════════════════════════════════

# Prefix form: "查/查询/查看 [name] [record keyword]"  (record keyword REQUIRED)
# e.g. "查张三病历", "查询华宁历史记录"
# Bare-name queries ("查张三") are deferred to LLM — too broad for fast path.
_QUERY_PREFIX_RE = re.compile(
    r"^(?:再)?(?:帮我查|查询|查看|查一下|看一下|查)\s*(?:患者|病人)?[：:\s]*\s*([\u4e00-\u9fff]{2,3}?)\s*"
    r"(?:的)?(?:历史|全部|所有|既往)?\s*" + _RECORD_KW + r"$"
)

# Suffix form: "[name] 的 [record keyword]"
# e.g. "李梦妍的病历", "张三的病情"
# End-anchored — trailing text like "张三的病历太旧了" should go to LLM.
_QUERY_SUFFIX_RE = re.compile(
    r"^" + _NAME_PAT + r"\s*的\s*" + _RECORD_KW + r"$"
)

# Name+keyword form: "[name][record keyword]" (no 的, no prefix verb)
# e.g. "张三病历"
_QUERY_NAME_QUESTION_RE = re.compile(
    r"^" + _NAME_PAT + r"\s*" + _RECORD_KW + r"$"
)

# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Supplement / continuation (add_record)
# ══════════════════════════════════════════════════════════════════════════════

# Explicit continuation markers — only unambiguous colon-delimited prefixes.
# Broader supplement triggers (记录一下, 本次记录, 加上…) are deferred to LLM.
_SUPPLEMENT_RE = re.compile(
    r"^(?:补充[：:。\s]|补一句[：:。\s]?|追加[：:]|补录[：:。\s])"
)


# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Create patient
# ══════════════════════════════════════════════════════════════════════════════

# Leading keyword: only "创建[患者/病人]NAME" and "新建[患者/病人]NAME" — anchored.
# Broader create triggers (新患者, 添加患者, 录入, 新收, 确认患者…) deferred to LLM.
_CREATE_LEAD_RE = re.compile(
    r"^(?:创建|新建)\s*(?:患者|病人)?\s*" + _NAME_PAT
    # Guard: name must be followed by demographic separator or end-of-string
    + r"(?=[，,。！？\s男女\d]|$)"
)

# Duplicate: "再建一个同名患者：NAME"
_CREATE_DUPLICATE_RE = re.compile(
    r"^再(?:建|来)一个同名(?:患者|病人)?[：:，,\s]*" + _NAME_PAT
)

# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Delete patient
# ══════════════════════════════════════════════════════════════════════════════

# Leading: "删除/删掉/移除 [患者/病人] [name]"
_DELETE_LEAD_RE = re.compile(
    r"^(?:删除|删掉|移除|删)(?:患者|病人)?\s*" + _NAME_PAT_4 + r"\s*$"
)

# Trailing: "把[name]删了/删掉" or "[name]删除"
_DELETE_TRAIL_RE = re.compile(
    r"^(?:把\s*)?" + _NAME_PAT_4 + r"\s*(?:删了|删掉|删除|移除)\s*$"
)

# With occurrence index: "删除第2个患者NAME"
_DELETE_OCCINDEX_RE = re.compile(
    r"^(?:如果有重复名字[，,]?\s*)?"
    r"(?:删除|删掉|移除|删)第\s*" + _TASK_NUM + r"\s*个(?:患者|病人)?\s*" + _NAME_PAT_4 + r"[。]?\s*$"
)

# ══════════════════════════════════════════════════════════════════════════════
# Tier 2 — Update patient demographics
# ══════════════════════════════════════════════════════════════════════════════

# "修改王明的年龄为50岁" / "王明的年龄改为50"
_UPDATE_PATIENT_DEMO_RE = re.compile(
    r"(?:修改|更新|更改|纠正|调整|把)\s*(?!病历|记录|情况|病情|状态|诊断|治疗)([\u4e00-\u9fff]{2,3})\s*的\s*(?:年龄|性别)"
    r"|(?!病历|记录|情况|病情|状态|诊断|治疗)([\u4e00-\u9fff]{2,3})\s*的\s*(?:年龄|性别)\s*(?:应该是|改为|更正为|更新为|改成|是)\s*[\d女男]"
)

# ══════════════════════════════════════════════════════════════════════════════
# Pending-record continuation guards
# ══════════════════════════════════════════════════════════════════════════════

# Abort/confirm tokens: short standalone messages that end the draft.
_PENDING_RECORD_ABORT_RE = re.compile(
    r"^(?:"
    r"确认|保存|提交|好的|确定|没了|就这样|就这些"        # confirm
    r"|取消|算了|不要|不用了|放弃|撤销|清空|重来|不对|重新|先不|不记了"  # abort
    r")[了吗的呢吧。！？\s]*$"
)

# Command-prefix guard: text starting with an explicit command verb should NOT
# be hijacked as pending-record continuation — fall through to LLM instead.
_PENDING_COMMAND_PREFIX_RE = re.compile(
    r"^(?:再)?(?:帮我)?(?:"
    r"查询|查看|查一下|看一下|查"            # query
    r"|创建|新建|建个|建一个|先创建|先建"     # create
    r"|删除|删掉|移除"                       # delete
    r"|预约|约一个"                           # appointment
    r"|导出|输出|生成报告"                    # export
    r"|给\S{2,3}设|安排"                     # follow-up / schedule
    r"|看下.*(?:待办|任务)|我的(?:待办|任务)" # list tasks
    r"|所有患者|全部患者|患者列表"            # list patients
    r")"
)

# ══════════════════════════════════════════════════════════════════════════════
# Record correction — name extraction
# ══════════════════════════════════════════════════════════════════════════════

# Name at message start for record correction / tier 3 name extraction.
_TIER3_NAME_RE = re.compile(
    r"^(?:患者|病人)?\s*([\u4e00-\u9fff]{2,3})[，,。：:\s男女\d]"
)
