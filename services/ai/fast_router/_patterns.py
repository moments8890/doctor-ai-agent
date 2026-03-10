"""
Compiled regex patterns and pure helpers for fast_router.

No intra-package dependencies — safe to import directly everywhere.
All patterns here are immutable after module load.
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


# ── Import history detection ───────────────────────────────────────────────────
_IMPORT_DATE_RE = re.compile(r"\d{4}[-/年]\d{1,2}")

# ── Tier 1: Flex patterns ──────────────────────────────────────────────────────
# "先看下.*待办" / "再给我所有患者" that don't fit exact sets
_LIST_TASKS_FLEX_RE = re.compile(
    r"^(?:先|再)?(?:看下|看一下|查看|查一下)\s*(?:我?(?:还有|今天有?|最近|今天的?)?(?:几个|哪些|什么)?\s*)"
    r"(?:待办|任务)(?:吗|呢|？)?$"
)
_LIST_PATIENTS_FLEX_RE = re.compile(
    r"^(?:再|先)?(?:给我|帮我看|看一下)?\s*(?:所有|全部|所有的|全部的)?\s*(?:患者|病人)(?:列表|名单|信息)?$"
)

# ── Chinese name pattern ───────────────────────────────────────────────────────
# Names: 2-3 chars (most Chinese names); 4-char names are rare and we avoid
# greedily consuming keywords that follow.
_NAME_PAT = r"([\u4e00-\u9fff]{2,3})"

# Record-domain keywords that follow a name (not part of the name)
_RECORD_KW = r"(?:病历|记录|情况|病情|近况|状态)"

# ── Tier 2: Regex patterns ─────────────────────────────────────────────────────

# Supplement / continuation add_record:
# "补充：…", "补一句：…", "加上…", "再补充…" are unambiguously record additions.
# This covers the single most common LLM-fallback pattern in real chatlogs:
#   "补充：建议门诊随访，按计划复查。"  (appears 895× in e2e corpus)
# Export: 导出/打印/下载 [name] 的病历/记录/报告
_EXPORT_RE = re.compile(
    # Negative lookahead prevents domain keywords (病历/记录/…) being captured as a name.
    r"^(?:帮我)?(?:导出|打印|下载|生成)\s*(?!病历|记录|报告|医疗记录)([\u4e00-\u9fff]{2,4}?)\s*(?:的)?\s*(?:病历|记录|报告|医疗记录)?(?:pdf|PDF)?$"
)
_EXPORT_NONAME_RE = re.compile(
    r"^(?:帮我)?(?:导出|打印|下载|生成)\s*(?:(?:目前|当前|这个|这位|患者)的?)?\s*(?:病历|记录|报告|医疗记录)(?:pdf|PDF)?$"
    # Context-triggered export: "准备会诊用", "会诊前导出", "MDT用", "需要病历文件"
    r"|^(?:准备会诊|会诊用|MDT用|需要病历文件)[。！\s]*$"
    r"|^(?:导出|打印|下载).{0,20}(?:会诊|MDT|全部记录|所有记录)\s*$"
)

# Outpatient report (卫生部 2010 门诊病历 standard format)
# Trigger phrases: 标准病历/门诊病历/卫生部病历/正式病历 with optional patient name
_OUTPATIENT_REPORT_RE = re.compile(
    r"^(?:帮我)?(?:生成|导出|打印|下载)\s*(?!标准门诊病历|门诊病历|卫生部病历|正式病历|标准病历)([\u4e00-\u9fff]{2,4}?)\s*(?:的)?\s*"
    r"(?:标准门诊病历|门诊病历|卫生部病历|正式病历|标准病历)(?:pdf|PDF)?$"
)
_OUTPATIENT_REPORT_NONAME_RE = re.compile(
    r"^(?:帮我)?(?:生成|导出|打印|下载)\s*(?:(?:目前|当前|这个|这位|患者)的?)?\s*"
    r"(?:标准门诊病历|门诊病历|卫生部病历|正式病历|标准病历)(?:pdf|PDF)?$"
)

_SUPPLEMENT_RE = re.compile(
    # Mixed anchoring is intentional:
    #   branches WITH trailing $ (写进去, 记进展…) are standalone-only triggers;
    #   branches WITHOUT $ (先记下, 补录…) are prefix triggers — clinical content follows.
    r"^(?:补充[：:。\s]|补一句[：:。\s]?|再补充|加上.{0,8}[，,]?|追加[：:]"
    r"|(?:好[，,]?\s*)?写进去[。！]?$"
    # Terse add_record triggers — short doctor phrases that unambiguously mean
    # "add a record for the current patient" (patient context inferred from history).
    # Using `.match()` so implicit ^ at start; $ inside last-alt anchors end-of-message.
    r"|先记下[，,。！\s]"          # "先记下，TIA发作…"
    r"|先续记[，,。！\s]?"         # "RICU这位先续记" — can end immediately
    r"|补录[：:。\s]"              # "补录：体温正常…"
    r"|补记录[：:。\s]"            # "补记录：换药完…"
    r"|先补记录[，,。！\s：:]?"     # "先补记录再约复诊" or "先补记录：..."
    r"|记进展[，,。！\s]?$"        # "记进展" as standalone or short phrase
    r"|就这样记[，,。！]"          # "就这样记，肿瘤科会诊后…"
    r"|补条记录[，,。！\s]?"       # "补条记录"
    r"|再记一条[，,。！\s]?"       # "导出前再记一条"
    r"|顺手补病程[，,。！\s]?"     # "顺手补病程"
    r"|先补病程[，,。！\s]?"       # "这位先补病程"
    r"|这位先补[，,。！\s：:]"     # "这位先补：…"
    r")"
)

# ── Tier 2: schedule_follow_up ─────────────────────────────────────────────────
# "给张三设3个月后随访提醒", "张三3个月后复诊", "三个月后随访张三"
_CN_NUM = r"[一两二三四五六七八九十\d]+"

# Single unified map — used by both _cn_or_arabic (follow-up scheduling) and
# _parse_task_num (task indexing).  Covers the full range that the Chinese-numeral
# regex _CN_NUM / _CN_DIGIT can produce, including two-character compounds.
_CN_NUM_MAP = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
}


def _cn_or_arabic(s: str) -> int:
    """Parse a Chinese or Arabic numeral string.

    Raises ValueError for unrecognised tokens so callers see an explicit
    failure instead of silently scheduling a 1-day follow-up.
    """
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


_TIME_UNIT = r"(?:天|日|周|个月|月)"
_FOLLOW_UP_KW = r"(?:随访|复诊|复查|随诊|随访提醒|复查提醒)"

_LAZY_NAME_PAT = r"([\u4e00-\u9fff]{2,3}?)"
_RELATIVE_TIME = r"(?:下周|下个月|下次|明天|后天|近期)"

# ── Tier 2: schedule_appointment ───────────────────────────────────────────────
# "给张三预约下周三10点", "约李明3月15号上午", "帮王五安排复诊明天下午"
_DATE_TIME_PAT = (
    r"(?:"
    r"\d+月\d+[日号]"          # 3月15日
    r"|下周[一二三四五六七日]?"  # 下周三
    r"|" + _RELATIVE_TIME +
    r")"
    r"(?:\s*\d{1,2}[点时:：]\d{0,2})?"  # optional hour
)
# Time is required: "给张三预约" without a date is semantically incomplete and
# too close to generic follow-up/task-creation to route with confidence.
_APPOINTMENT_RE = re.compile(
    r"^(?:给|为|帮|替)?\s*" + _LAZY_NAME_PAT + r"\s*"
    r"(?:预约|约诊|挂号|安排(?:复诊|门诊|预约))\s*"
    r"(?:" + _DATE_TIME_PAT + r")\s*$"
)
_APPOINTMENT_VERB_FIRST_RE = re.compile(
    r"^(?:预约|约)\s*" + _LAZY_NAME_PAT + r"\s*"
    r"(?:" + _DATE_TIME_PAT + r")\s*$"
)

_FOLLOWUP_WITH_NAME_RE = re.compile(
    r"^(?:给|为)?\s*" + _LAZY_NAME_PAT + r"\s*"
    r"(?:设|安排|创建|建|定)?\s*"
    r"(?:(" + _CN_NUM + r")\s*(" + _TIME_UNIT + r")后)?\s*"
    + _FOLLOW_UP_KW + r"(?:提醒)?$"
)
_FOLLOWUP_LEAD_TIME_RE = re.compile(
    r"^(?:给|为)?\s*" + _LAZY_NAME_PAT + r"\s*"
    r"(?:设|安排|创建|建|定)?\s*"
    r"(?:(" + _CN_NUM + r")\s*(" + _TIME_UNIT + r")后)\s*"
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

# Follow-up without explicit patient name — relies on session context to fill in name.
# Covers: "3个月后随访", "安排复查", "设个随访提醒", "下次复诊记一下", "给他安排随访"
_FOLLOWUP_NONAME_RELATIVE_RE = re.compile(
    r"^(?:给(?:他|她|这位|这个)|帮(?:他|她|这位))?\s*"
    r"(?:设|安排|创建|建|定)?\s*"
    r"(下周|下个月|下次|近期|明天|后天)\s*"
    r"(?:随访|复诊|复查|随诊)(?:提醒)?$"
)
_FOLLOWUP_NONAME_RE = re.compile(
    # Bare "随访"/"复查" with no pronoun and no time is too weak to route with
    # confidence; require at least one substantive signal.
    r"^(?:"
    # Branch A: explicit pronoun — "给他/她/这位 [verb] [time] 随访"
    r"(?:给(?:他|她|这位|这个)|帮(?:他|她|这位))\s*"
    r"(?:设|安排|创建|建|定)?\s*"
    r"(?:(?:[一两二三四五六七八九十\d]+)\s*(?:天|日|周|个月|月)后\s*)?"
    r"(?:随访|复诊|复查|随诊|随访提醒|复查提醒)(?:提醒)?"
    r"|"
    # Branch B: explicit time clause — "N单位后 随访" (no pronoun needed)
    r"(?:设|安排|创建|建|定)?\s*"
    r"(?:[一两二三四五六七八九十\d]+)\s*(?:天|日|周|个月|月)后\s*"
    r"(?:随访|复诊|复查|随诊|随访提醒|复查提醒)(?:提醒)?"
    r")$"
)

# ── Tier 2: postpone_task ──────────────────────────────────────────────────────
# "推迟任务3一周", "任务2延后3天", "任务5推后两天"
_POSTPONE_TASK_RE = re.compile(
    r"^(?:推迟|延迟|推后|延后)\s*任务\s*([一两二三四五六七八九十\d]+)\s*"
    r"(" + _CN_NUM + r")\s*(" + _TIME_UNIT + r")$"
)
_POSTPONE_TASK_B_RE = re.compile(
    r"^任务\s*([一两二三四五六七八九十\d]+)\s*(?:推迟|延迟|推后|延后)\s*"
    r"(" + _CN_NUM + r")\s*(" + _TIME_UNIT + r")$"
)

# ── Tier 2: cancel_task ────────────────────────────────────────────────────────
# "取消任务3", "任务2取消", "取消第3个任务"
_CANCEL_TASK_A_RE = re.compile(r"^取消任务([一两二三四五六七八九十\d]+)$")
_CANCEL_TASK_B_RE = re.compile(r"^任务([一两二三四五六七八九十\d]+)取消$")
_CANCEL_TASK_C_RE = re.compile(r"^取消第([一两二三四五六七八九十\d]+)(?:个|条)?任务$")

# Query: 查/查询/查看/查一下/帮我查/再查一下 [name] + optional record keyword + trailing text
# Record keyword is optional (e.g. "查张三" / "查询华宁" with no trailing keyword).
# Allow trailing text (e.g. "查询张三的病历概要", "查询赵峰历史病历").
_QUERY_PREFIX_RE = re.compile(
    r"^(?:再)?(?:帮我查|查询|查看|查一下|看一下|查)\s*(?:患者|病人)?[：:\s]*\s*([\u4e00-\u9fff]{2,3}?)\s*"
    r"(?:的)?(?:(?:历史|全部|所有)?\s*" + _RECORD_KW + r"\S*)?$"
)

# Query: [name] + 的 + record keyword + optional trailing text
_QUERY_SUFFIX_RE = re.compile(
    r"^" + _NAME_PAT + r"\s*的\s*" + _RECORD_KW + r".*$"
)

# Query: [name] immediately followed by record keyword (no 的)
_QUERY_NAME_QUESTION_RE = re.compile(
    r"^" + _NAME_PAT + r"\s*" + _RECORD_KW + r"$"
)

# Create: leading keyword directly before the name.
# Longer alternatives listed first so Python re tries them left-to-right.
# Separator allows whitespace, comma, or colon (e.g. "先建档：陈涛").
_CREATE_LEAD_RE = re.compile(
    r"(?:"
    r"帮我建个新患者|帮我建个新病人|帮我加个患者|帮我加个病人"
    r"|建个新患者|建个新病人"
    r"|新建患者|新建病人"
    r"|添加患者|添加病人"
    r"|加个患者|加个病人"
    r"|录入患者|录入病人"
    r"|新患者|新病人"
    r"|建个新档|先建个档|先建档"  # e.g. "先建个档：乔慕言", "建个新档，贺清和"
    r"|新收[：:]?"                # e.g. "神经内科新收：顾清妍"
    r"|建档"
    r")"
    r"[\s,，：:]*" + _NAME_PAT
    # Guard: the extracted name must be followed by a demographic separator or
    # end-of-string to prevent false matches like "建档并保存" → name="并保".
    + r"(?=[，,。！？\s男女\d]|$)"
)

# Create duplicate: "再建一个同名：NAME,gender,age" / "再来一个同名患者：NAME"
# Corpus pattern appears 13× (one per test case with duplicate-name scenario).
_CREATE_DUPLICATE_RE = re.compile(
    r"^再(?:建|来)一个同名(?:患者|病人)?[：:，,\s]*" + _NAME_PAT
)

# Create: "[name] + trailing keyword"
_CREATE_TRAIL_RE = re.compile(
    _NAME_PAT + r"\s*(?:新患者|新病人|建档|建个档)"
)

# Create: terse "[name] [gender/age/clinical...] 建档" at end of message
# e.g. "王琴 女47 胆囊术后D1 建档", "林若安，女，78岁，...建档"
# Separator after name is whitespace or Chinese comma/punctuation.
_CREATE_TERSE_END_RE = re.compile(
    r"^(" + _NAME_PAT[1:-1] + r")[，,\s]+(?:[男女\d]|\w).*?(?:建档|建个档|先建档|先建个档)\s*$"
)

# Demographics helpers
_GENDER_RE = re.compile(r"[男女](?:性)?")
_AGE_RE = re.compile(r"(\d{1,3})\s*岁")

# Delete patterns use a 4-char name variant: a wrong match on a destructive
# action is unacceptable, and compound surnames (司徒, 欧阳, 上官…) yield 4-char names.
_NAME_PAT_4 = r"([\u4e00-\u9fff]{2,4})"

# Delete leading: "删除/删掉/移除 [患者/病人] [name]"
_DELETE_LEAD_RE = re.compile(
    r"^(?:删除|删掉|移除|删)(?:患者|病人)?\s*" + _NAME_PAT_4 + r"\s*$"
)

# Delete trailing: "把[name]删了/删掉" or "[name]删除/删掉"
_DELETE_TRAIL_RE = re.compile(
    r"^(?:把\s*)?" + _NAME_PAT_4 + r"\s*(?:删了|删掉|删除|移除)\s*$"
)

# Complete task: "完成任务N", "完成N", "标记N完成", "任务N完成", "N完成"
# N may be Arabic digits or Chinese ordinals.
# Split into patterns to avoid duplicate named-group error.
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
# Pattern D: "把第N条标记完成" / "把第N条完成" (e2e corpus variant, 20× occurrences)
_COMPLETE_TASK_D_RE = re.compile(
    r"^把第\s*" + _TASK_NUM + r"\s*条(?:\s*标记)?\s*" + _DONE_WORDS + r"[。！]?\s*$"
)
# Delete with occurrence index: "删除第N个患者NAME" / "删除第N个NAME"
# Also handles conditional prefix: "如果有重复名字，删除第二个患者NAME" (10× in e2e corpus).
_DELETE_OCCINDEX_RE = re.compile(
    r"^(?:如果有重复名字[，,]?\s*)?"
    r"(?:删除|删掉|移除|删)第\s*" + _TASK_NUM + r"\s*个(?:患者|病人)?\s*" + _NAME_PAT_4 + r"[。]?\s*$"
)

def _parse_task_num(raw: str) -> Optional[int]:
    if raw.isdigit():
        return int(raw)
    return _CN_NUM_MAP.get(raw)


# ── Update patient demographics ───────────────────────────────────────────────
# "修改王明的年龄为50岁" / "更新李华的性别为女" / "王明的年龄改为50" / "把X的性别改成女"
# Negative lookahead before the name slot guards against domain nouns (病历, 诊断…)
# landing in the name capture; downstream _NON_NAME_KEYWORDS provides a second pass.
_UPDATE_PATIENT_DEMO_RE = re.compile(
    r"(?:修改|更新|更改|纠正|调整|把)\s*(?!病历|记录|情况|病情|状态|诊断|治疗)([\u4e00-\u9fff]{2,3})\s*的\s*(?:年龄|性别)"
    r"|(?!病历|记录|情况|病情|状态|诊断|治疗)([\u4e00-\u9fff]{2,3})\s*的\s*(?:年龄|性别)\s*(?:应该是|改为|更正为|更新为|改成|是)\s*[\d女男]"
)

# ── Record correction ─────────────────────────────────────────────────────────
# Triggered when doctor explicitly acknowledges a previous record error.
_CORRECT_RECORD_RE = re.compile(
    r"刚才.{0,20}(?:写错了|有误|错误|不对|记错了|搞错了)"
    r"|上一条.{0,15}(?:有误|写错了|错误|不对)"
    r"|(?:病历|记录).{0,15}(?:写错了|有误|搞错了|记错了)"
    r"|(?:更正|纠正).{0,5}(?:上一条|刚才|最近)?.{0,5}(?:病历|记录)"
    # Natural-language field corrections: "主诉改为…", "诊断调整为…", "不是X是Y"
    r"|(?:主诉|诊断|治疗|用药|处置|病史|手术|年龄|性别).{0,6}(?:改为|改成|更正为|更新为|应该是|调整为)"
    r"|(?:不是|非).{1,10}(?:是|，|,).{0,10}(?:对|才对|才是对的|正确)"
    r"|(?:应该|应是|应为).{0,4}(?:主诉|诊断|治疗|用药|手术)"
)

# Name extraction for correction messages where name follows "刚才/上一条".
# E.g. "刚才李波的主诉写错了" → "李波"
#      "上一条陈刚的诊断有误" → "陈刚"
_CORRECT_NAME_RE = re.compile(
    r"(?:刚才|上一条(?:病历|记录)?)\s*([\u4e00-\u9fff]{2,3})\s*的"
    r"|(?:更正|纠正)\s*\S{0,5}\s*([\u4e00-\u9fff]{2,3})\s*的(?:病历|记录)"
)

# Name at message start: "张三，…" / "患者张三" / "病人李明"
# Also used by _tier3.py and _router.py.
# Best-effort only: the following-char set [，,。：:\s男女\d] intentionally excludes
# bare Chinese characters to avoid greedily consuming clinical terms as part of the
# name (e.g. "张三胸痛" would capture "张三胸").  Callers MUST apply _TIER3_BAD_NAME
# filtering — this regex is not sufficient on its own.
_TIER3_NAME_RE = re.compile(
    r"^(?:患者|病人)?\s*([\u4e00-\u9fff]{2,3})[，,。：:\s男女\d]"
)


def _extract_demographics(text: str) -> tuple[Optional[str], Optional[int]]:
    """Extract gender and age from a message fragment."""
    gm = _GENDER_RE.search(text)
    gender: Optional[str] = gm.group(0)[0] if gm else None  # just 男/女
    am = _AGE_RE.search(text)
    age: Optional[int] = int(am.group(1)) if am else None
    return gender, age
