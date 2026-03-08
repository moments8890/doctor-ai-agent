"""
基于关键词、正则和临床启发式规则的快速意图路由，无需调用 LLM，90% 以上的指令在 1ms 内响应。
"""

from __future__ import annotations

import json
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.ai.intent import Intent, IntentResult

# ── Tier-3 binary classifier (TF-IDF + logistic regression) ──────────────────
# Loaded once at import; used as the final gate in _is_clinical_tier3().
# Falls back to True (old behaviour) if the model file is absent — i.e. the
# system works without the classifier, just with the old ~10-19% FP hard floors.
_TIER3_CLASSIFIER = None
_TIER3_CLASSIFIER_PATH = Path(__file__).parent / "tier3_classifier.pkl"

def _load_tier3_classifier() -> None:
    global _TIER3_CLASSIFIER
    if _TIER3_CLASSIFIER_PATH.exists():
        try:
            with _TIER3_CLASSIFIER_PATH.open("rb") as _f:
                _TIER3_CLASSIFIER = pickle.load(_f)
        except Exception:
            _TIER3_CLASSIFIER = None

_load_tier3_classifier()

# ── Import history detection ───────────────────────────────────────────────────
_IMPORT_KEYWORDS: frozenset[str] = frozenset()
_IMPORT_DATE_RE = re.compile(r"\d{4}[-/年]\d{1,2}")

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

_LIST_PATIENTS_EXACT: frozenset[str] = frozenset()
# Very short triggers — only match if the entire message is exactly these chars
_LIST_PATIENTS_SHORT: frozenset[str] = frozenset()

_LIST_TASKS_EXACT: frozenset[str] = frozenset()
_LIST_TASKS_SHORT: frozenset[str] = frozenset()

# Flex patterns: "先看下.*待办" / "再给我所有患者" that don't fit exact sets
_LIST_TASKS_FLEX_RE = re.compile(
    r"^(?:先|再)?(?:看下|看一下|查看|查一下)\s*(?:我?(?:还有|今天有?|最近|今天的?)?(?:几个|哪些|什么)?\s*)"
    r"(?:待办|任务)(?:吗|呢|？)?$"
)
_LIST_PATIENTS_FLEX_RE = re.compile(
    r"^(?:再|先)?(?:给我|帮我看|看一下)?\s*(?:所有|全部|所有的|全部的)?\s*(?:患者|病人)(?:列表|名单|信息)?$"
)

# ── Domain keywords that must never be treated as patient names ────────────────
_NON_NAME_KEYWORDS: frozenset[str] = frozenset()

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
    r"^(?:帮我)?(?:导出|打印|下载|生成)\s*([\u4e00-\u9fff]{2,4}?)\s*(?:的)?\s*(?:病历|记录|报告|医疗记录)?(?:pdf|PDF)?$"
)
_EXPORT_NONAME_RE = re.compile(
    r"^(?:帮我)?(?:导出|打印|下载|生成)\s*(?:(?:目前|当前|这个|这位|患者)的?)?\s*(?:病历|记录|报告|医疗记录)(?:pdf|PDF)?$"
)

# Outpatient report (卫生部 2010 门诊病历 standard format)
# Trigger phrases: 标准病历/门诊病历/卫生部病历/正式病历 with optional patient name
_OUTPATIENT_REPORT_RE = re.compile(
    r"^(?:帮我)?(?:生成|导出|打印|下载)\s*([\u4e00-\u9fff]{2,4}?)\s*(?:的)?\s*"
    r"(?:标准门诊病历|门诊病历|卫生部病历|正式病历|标准病历)(?:pdf|PDF)?$"
)
_OUTPATIENT_REPORT_NONAME_RE = re.compile(
    r"^(?:帮我)?(?:生成|导出|打印|下载)\s*(?:(?:目前|当前|这个|这位|患者)的?)?\s*"
    r"(?:标准门诊病历|门诊病历|卫生部病历|正式病历|标准病历)(?:pdf|PDF)?$"
)

_SUPPLEMENT_RE = re.compile(
    r"^(?:补充[：:。\s]|补一句[：:。\s]?|再补充|加上.{0,8}[，,]?|追加[：:]"
    r"|(?:好[，,]?\s*)?写进去[。！]?$)"
)

# ── Tier 2: schedule_follow_up ─────────────────────────────────────────────────
# "给张三设3个月后随访提醒", "张三3个月后复诊", "三个月后随访张三"
_CN_NUM = r"[一两二三四五六七八九十\d]+"

_CN_DIGIT_MAP = {
    "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _cn_or_arabic(s: str) -> int:
    return _CN_DIGIT_MAP.get(s, 0) or (int(s) if s.isdigit() else 1)


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
    r"^(?:再)?(?:帮我查|查询|查看|查一下|看一下|查)\s*([\u4e00-\u9fff]{2,3}?)\s*"
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
    r"(?:删除|删掉|移除|删)第\s*" + _TASK_NUM + r"\s*个(?:患者|病人)?\s*" + _NAME_PAT + r"[。]?\s*$"
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


# ── Update patient demographics ───────────────────────────────────────────────
# "修改王明的年龄为50岁" / "更新李华的性别为女" / "王明的年龄改为50" / "把X的性别改成女"
_UPDATE_PATIENT_DEMO_RE = re.compile(
    r"(?:修改|更新|更改|纠正|调整|把)\s*" + _NAME_PAT + r"\s*的\s*(?:年龄|性别)"
    r"|" + _NAME_PAT + r"\s*的\s*(?:年龄|性别)\s*(?:应该是|改为|更正为|更新为|改成|是)\s*[\d女男]"
)

# ── Record correction ─────────────────────────────────────────────────────────
# Triggered when doctor explicitly acknowledges a previous record error.
_CORRECT_RECORD_RE = re.compile(
    r"刚才.{0,20}(?:写错了|有误|错误|不对|记错了|搞错了)"
    r"|上一条.{0,15}(?:有误|写错了|错误|不对)"
    r"|(?:病历|记录).{0,15}(?:写错了|有误|搞错了|记错了)"
    r"|(?:更正|纠正).{0,5}(?:上一条|刚才|最近)?.{0,5}(?:病历|记录)"
)

# Name extraction for correction messages where name follows "刚才/上一条".
# E.g. "刚才李波的主诉写错了" → "李波"
#      "上一条陈刚的诊断有误" → "陈刚"
_CORRECT_NAME_RE = re.compile(
    r"(?:刚才|上一条(?:病历|记录)?)\s*([\u4e00-\u9fff]{2,3})\s*的"
    r"|(?:更正|纠正)\s*\S{0,5}\s*([\u4e00-\u9fff]{2,3})\s*的(?:病历|记录)"
)

# ── Tier 3: clinical keyword set ───────────────────────────────────────────────
# High-specificity terms that strongly imply clinical content. Conservative — if
# a keyword could appear in a non-clinical question, it is omitted here. Border-
# line messages still fall through to the routing LLM.
_CLINICAL_KW_TIER3: frozenset[str] = frozenset({
    # Cardinal symptoms
    "胸痛", "胸闷", "心悸", "气促", "气短", "头痛", "发热", "发烧",
    "咳嗽", "腹痛", "恶心", "呕吐", "乏力", "眩晕", "水肿",
    "呼吸困难", "阵发性", "晕厥", "心绞痛", "发绀",
    # Cardiovascular diagnoses / procedures
    "心衰", "心梗", "房颤", "STEMI", "PCI", "溶栓", "消融", "支架",
    # Oncology
    "化疗", "靶向", "放疗", "肿瘤", "升白",
    # Specific lab markers (unlikely in non-clinical speech)
    "BNP", "肌钙蛋白", "HbA1c", "CEA", "ANC", "EGFR", "HER2",
    "INR", "血常规", "抗凝",
    # Prescribing action ("give/administer" — almost always clinical)
    "给予",
    # Follow-up / re-check — almost always in a clinical note context.
    # Guard: messages that only contain 复查 + 提醒 (reminder setting) go to LLM.
    "复查",
    # English clinical terms (mixed-language doctor notes)
    "chest", "ECG", "NIHSS", "dyspnea", "palpitation",
    # Neurological (CBLUE-expanded)
    "颅内高压", "颅内压增高", "颅压高", "脑水肿", "脑疝", "颅内肿瘤", "颅内占位性病变",
    "视乳头水肿",
    # Metabolic / systemic (CBLUE-expanded)
    "低血糖", "高氨血症", "代谢性酸中毒", "黄疸",
    # Cardiology (CBLUE-expanded)
    "胸腔积液", "室间隔缺损", "动脉导管未闭", "大动脉转位",
    # Common symptoms (CBLUE-expanded)
    "高热", "肺炎", "便秘",
    # Signs / oncology (CBLUE-expanded)
    "淋巴结转移", "血管瘤",
    # Procedures / drugs (CBLUE-expanded)
    "腰椎穿刺", "抗生素",
    # Symptoms — local dataset mined (RAG 80k + CMedQA2 + CMExam)
    "疼痛", "头晕", "腰痛", "痛经", "肿胀", "全身无力", "四肢无力",
    "面色苍白", "压痛", "无压痛", "反跳痛", "腹泻", "腹胀",
    "咽痛", "咽喉肿痛", "胃痛", "乳房胀痛", "刺痛", "红肿",
    "头晕耳鸣", "偏头痛", "三叉神经痛", "心慌", "浮肿", "肿块",
    # Diseases — local dataset mined
    "高血压", "糖尿病", "颈椎病", "冠心病", "心律失常", "心脏病",
    "肺结核", "肺癌", "肺气肿", "胸膜炎", "高脂血症", "低血压",
    "胃炎", "盆腔炎", "妇科炎症", "阴道炎", "子宫内膜炎", "前列腺炎",
    "鼻炎", "低蛋白血症", "高血压病史", "脑血管病", "椎管狭窄",
    "乳腺增生", "囊肿",
    # Signs / lab — local dataset mined
    "心电图", "白细胞", "血红蛋白", "出血", "尿痛",
    # Lab markers (discovered from personal test documents)
    "空腹血糖", "餐后血糖", "血糖升高", "血糖偏高", "血糖控制", "血糖异常",
    # Neurological / cerebrovascular (from 烟雾病 patient records)
    "烟雾病", "视野缺损", "视野缩窄", "脑梗", "脑梗死", "脑梗塞",
    "脑动脉", "颅内动脉", "颅外颅内", "搭桥手术",
})

# ── Extra Tier-3 keywords loaded from data/fast_router_keywords.json ─────────
# Starts empty; populated by load_extra_keywords() at module import time.
# Use reload_extra_keywords() for hot-reload without restart.
_EXTRA_KW_TIER3: frozenset[str] = frozenset()
_EXTRA_KW_PATH = "config/fast_router_keywords.json"

# These are also populated by load_extra_keywords(); declared here so that the
# module-level assignments in load_extra_keywords() don't get clobbered by
# declarations that appear after the load call.
_TIER3_BAD_NAME: frozenset[str] = frozenset()


def _load_kw_section(data: dict, key: str) -> frozenset[str]:
    """Extract keywords from a section that is either a list or {keywords: [...]}."""
    val = data.get(key, [])
    if isinstance(val, list):
        return frozenset(str(k) for k in val if k)
    if isinstance(val, dict):
        return frozenset(str(k) for k in val.get("keywords", []) if k)
    return frozenset()


def load_extra_keywords(path: str = _EXTRA_KW_PATH) -> int:
    """Load all keyword sets from the JSON config file.

    Populates the following module-level frozensets from the config:
    - ``_IMPORT_KEYWORDS`` — import_history triggers
    - ``_LIST_PATIENTS_EXACT`` / ``_LIST_PATIENTS_SHORT`` — list_patients triggers
    - ``_LIST_TASKS_EXACT`` / ``_LIST_TASKS_SHORT`` — list_tasks triggers
    - ``_NON_NAME_KEYWORDS`` — words excluded from patient-name extraction
    - ``_TIER3_BAD_NAME`` — words excluded from Tier-3 name extraction
    - ``_EXTRA_KW_TIER3`` / ``_CLINICAL_KW_TIER3`` — extra Tier-3 clinical terms

    Supports two category formats for the ``tier3`` section::

        # Object format (recommended) — with description/description_zh
        "tier3": {
          "<category>": {
            "description": "...",
            "description_zh": "...",
            "keywords": ["term1", "term2"]
          }
        }

        # Legacy list format
        "tier3": {"<category>": ["term1", "term2"]}

    Silently no-ops if the file does not exist.

    Returns the total number of keywords loaded across all sets.
    """
    global _EXTRA_KW_TIER3, _IMPORT_KEYWORDS, _LIST_PATIENTS_EXACT, _LIST_PATIENTS_SHORT
    global _LIST_TASKS_EXACT, _LIST_TASKS_SHORT, _NON_NAME_KEYWORDS, _CLINICAL_KW_TIER3, _TIER3_BAD_NAME
    p = Path(path)
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        _IMPORT_KEYWORDS = _load_kw_section(data, "import_keywords")
        _LIST_PATIENTS_EXACT = _load_kw_section(data, "list_patients_exact")
        _LIST_PATIENTS_SHORT = _load_kw_section(data, "list_patients_short")
        _LIST_TASKS_EXACT = _load_kw_section(data, "list_tasks_exact")
        _LIST_TASKS_SHORT = _load_kw_section(data, "list_tasks_short")
        _NON_NAME_KEYWORDS = _load_kw_section(data, "non_name_keywords")
        _TIER3_BAD_NAME = _load_kw_section(data, "tier3_bad_name")
        # tier3 handled separately (multi-category)
        tier3 = data.get("tier3", {})
        terms: list[str] = []
        for cat_value in tier3.values():
            if isinstance(cat_value, list):
                terms.extend(str(k) for k in cat_value if k)
            elif isinstance(cat_value, dict):
                for k in cat_value.get("keywords", []):
                    if k:
                        terms.append(str(k))
        _EXTRA_KW_TIER3 = frozenset(terms)
        _CLINICAL_KW_TIER3 = _EXTRA_KW_TIER3  # alias — tier3 is now fully in JSON
        return (
            len(_IMPORT_KEYWORDS)
            + len(_LIST_PATIENTS_EXACT)
            + len(_LIST_PATIENTS_SHORT)
            + len(_LIST_TASKS_EXACT)
            + len(_LIST_TASKS_SHORT)
            + len(_NON_NAME_KEYWORDS)
            + len(_TIER3_BAD_NAME)
            + len(_EXTRA_KW_TIER3)
        )
    except Exception:
        return 0


def reload_extra_keywords(path: str = _EXTRA_KW_PATH) -> dict:
    """Hot-reload extra Tier-3 keywords from disk.

    Returns a summary dict ``{"loaded": N, "path": path}``.
    """
    n = load_extra_keywords(path)
    return {"loaded": n, "path": path}


def get_extra_keywords() -> dict:
    """Return the full keywords config, all sections."""
    p = Path(_EXTRA_KW_PATH)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # Return all sections except metadata fields
        return {k: v for k, v in data.items() if k not in ("format", "description", "description_zh", "_comment")}
    except Exception:
        return {}


# Load at module import time (no-op if file absent).
load_extra_keywords()

# Name at message start: "张三，…" / "患者张三" / "病人李明"
_TIER3_NAME_RE = re.compile(
    r"^(?:患者|病人)?\s*([\u4e00-\u9fff]{2,3})[，,。：:\s男女\d]"
)


_REMINDER_RE = re.compile(r"提醒|设.*\d+[点时:：]|设.*复查提醒")

# ── Tier 3 patient-question guards ───────────────────────────────────────────
# Patient questions from lay users (CMedQA2 analysis: 45% FP rate without guards).
# These patterns identify text that is almost certainly a patient asking a
# question — not a doctor dictating a clinical note.

# Question-phrase signal: colloquial "what should I do", "why", "is it normal?"
# Extended with IMCS-DAC + CMedQA2 analysis: duration questions, choice questions,
# inquiry patterns, consultation-seeking phrases, and question-ending particles.
_TIER3_QUESTION_RE = re.compile(
    r"怎么办|怎么回事|是怎么回事|该怎么|是什么原因|有什么办法|有什么方法"
    r"|怎么治疗|如何治疗|会不会|能不能|吃什么药|是什么病"
    r"|有什么关系|正常吗|严重吗|有没有问题|是否严重"
    # Duration questions (IMCS-DAC: "咳嗽几天了", "发烧多长时间了")
    r"|几天了$|多久了$|多长时间|多少天了$"
    # Choice questions (IMCS-DAC: "是夜间严重还是白天严重")
    r"|是.{1,8}还是"
    # Inquiry pattern (IMCS-DAC: "有没有咳嗽", "有没有检查血常规")
    r"|有没有"
    # Question-ending particles — almost never appear at end of specialist clinical notes
    r"|了吗[？?]?$|吗[？?]?$|呢[？?]?$"
    # Consultation-seeking phrases (CMedQA2: patient Q&A forum patterns)
    r"|请问|请指教|请教|请.*帮.*解答|请.*分析"
    # Treatment-seeking verb variants missed before (CMedQA2: "怎样治疗")
    r"|怎样治疗|怎样用药|怎样处理|怎样调理"
    # Standalone question mark at sentence end (CMedQA2: 26% of patient question FPs)
    r"|[？?]\s*$"
    # Advice-seeking phrases
    r"|该如何|该怎样|应该怎么"
    # Structured patient portal format (Baidu list: "全部症状：…发病时间及原因：…")
    r"|全部症状[：:]|发病时间及原因|治疗情况[：:]|发病时间[：:]"
    # Medical knowledge queries — knowledge-seeking suffix patterns (Baidu finetune)
    r"|的鉴别诊断$|的并发症$|的并发症有|的症状有哪些|的诊断依据|的发病机制|的病因$|的病因有"
    r"|的治疗方法|的处理原则|的预防措施|的检查方法"
    # Medical exam MCQ stems (CMExam: "下列…属于", "正确的是", "错误的是")
    r"|^下列|^以下(?:哪|各)项|正确的是$|错误的是$|不正确的是$|不包括$"
    r"|属于.*的是$|应首选$|最可能.*诊断$|最佳.*是$"
    # Additional CMExam endings — non-vignette questions without doctor anchor
    # (vignette patterns handled by _TIER3_EXAM_ENDING_RE which ignores anchor)
    r"|考虑的是[：:]?\s*$|的(?:疾病|症状|体征|病因|改变|类型)是[：:]?\s*$"
    r"|(?:特点|原因|表现|机制|体征|检查|热型)是[：:]?\s*$"
    r"|(?:最?常?多?)见于\s*$|可见于\s*$|常伴有\s*$|放射至\s*$"
    r"|治疗应首选\s*$|意义的是[：:]?\s*$"
    r"|(?:药物|成药|方剂|措施|方法|方案|证候|证型|治法|病原体)是\s*$"
    r"|(?:并发症|不良反应)是\s*$|诊断为\s*$|部位在\s*$"
    # "哪种/哪项/哪个" — explicit question words in MCQ stems
    r"|哪种|哪项|哪个|哪类|哪些"
    # Bare 是/为 (optional colon) at sentence end; specific noun/verb endings
    r"|是[：:]?\s*$|为[：:]?\s*$|属于\s*$|体位\s*$|类型\s*$"
    r"|出现\s*$|宜用\s*$|选用\s*$|宜选用\s*$|不宜用\s*$"
    r"|何药|何种|何法"
    # CHIP-MDCFNPC / MedDG patient-turn FP guards (online consultation messages)
    # Patient demographic tag: "(男，45岁)" / "（女，32岁）" at message end
    # Handles both ASCII () and full-width （） parentheses
    r"|[（(](?:男|女)[，,]?\s*\d+岁[）)][。！]?\s*$"
    # Causal question: "引起的" at sentence end — patient asking cause of symptom
    r"|引起的[。？]?\s*$"
    # Soft question particles at sentence end — never in clinical dictation
    r"|吧[。！？]?\s*$|呀[。！？]?\s*$|么[？！]?\s*$"
    # Patient-addressing openers — patient talking TO a doctor
    r"|医生您好|医生你好|大夫您好|大夫你好"
    # Knowledge query suffix
    r"|什么意思[？。]?\s*$"
    # "是不是" — "is it or not" patient question pattern (CHIP-STS/MedDG)
    r"|是不是"
    # "能否" — "can or not" question (CHIP-STS: 80 FPs)
    r"|能否"
    # Knowledge lookup suffixes (CHIP-STS: patient disease queries)
    r"|的定义[？。]?\s*$|的危害[？。]?\s*$|的影响[？。]?\s*$|的护理[？。]?\s*$"
    # Bare "如何" at sentence end — "how?" without treatment verb (CHIP-STS)
    r"|如何[？。]?\s*$"
    # "吃什么" — generalises "吃什么药"; patient diet/medication queries (CHIP-STS)
    r"|吃什么"
    # "怎么样" at sentence end — "how is it?" (CHIP-STS: patient status queries)
    r"|怎么样[？。]?\s*$"
    # "有什么" food/medication/remedy queries — "xxx有什么症状/用药"
    r"|有什么.*(?:吗|呢)[？?]?\s*$"
    # Baidu encyclopedia format: "short question？long answer" concatenated.
    # Requires a question word (什么/如何/怎么/会…吗/多久/可以) before the ？
    # so that BP uncertainty "170/？mmhg" and differential "肿瘤？" are NOT matched.
    # The doctor anchor (收入我科/收入我院/门诊以/诊断) overrides for real clinical notes.
    r"|^.{0,35}(?:什么|如何|怎么|怎样|会.{0,8}吗|能.{0,8}吗|多久|可以|为什么|是否).{0,15}[？?].{20,}"
    # MedDialog-CN: patients describing family member's condition to an online doctor
    # "我妈妈...","我父亲...","我孩子..." — first-person family reference is near-absent in clinical notes
    r"|我(?:妈|爸|母亲|父亲|女儿|儿子|老公|老婆|爱人|孩子|宝宝|小孩|家人|丈夫|妻子)"
    # Patients addressing a specific doctor by title: "王主任，您好" / "李教授，您好"
    r"|[\u4e00-\u9fff]{1,4}(?:主任|教授)[，,]?您好"
    # Consultation-seeking openers missed by 请问 guard (MedDialog-CN / CMID)
    r"|(?:问一下|请教一下|咨询一下|想咨询|想请教|想问一下)"
    r"|(?:求助|求解答|帮我看看|帮忙看看|帮我分析)"
    # Gratitude to the doctor — patient closing phrase, never in clinical dictation
    r"|(?:感谢|谢谢|万分感谢)(?:医生|大夫|您|你)"
)

# First-person patient voice — two tiers:
# Tier A (original): "我…怎么办/会不会/？" — explicit question
# Tier B (CMedQA2): "我/本人…不舒服/疼痛/症状…" — patient self-description without
#   explicit question word (e.g. "我最近头痛，做过CT，不知该如何…").
_TIER3_PATIENT_VOICE_RE = re.compile(
    r"^(?:我|我家|我妈|我爸|我爷|我奶|我老|我儿|我女|我孩|我宝|我老婆|我丈夫|我先生)"
    r".{0,30}(?:怎么|是否|会不会|能不能|为什么|什么原因|[？?])"
    r"|^(?:我|本人).{0,50}(?:不舒服|不好|难受|疼痛|疼痛感|痒|肿胀|头晕|乏力|出血|不适|有症状|做了检查|做过检查|手术后|术后|患病|得了)"
)

# Online-consultation context: pediatric terms signal patient-facing consultation,
# not a specialist clinical note. (IMCS-DAC analysis: 42% of FPs contained these terms.)
# Bypassed by doctor-voice anchor (患者/患儿/主诉: etc.).
_TIER3_CONSULT_RE = re.compile(r"宝宝|宝贝|孩子|小孩")

# Doctor-voice anchor: overrides the question guards when present.
# A doctor may include a question within a clinical note.
# Clinical admission phrases (收入我科/收入我院/门诊以) are also anchors — they are
# exclusive to hospital documentation and never appear in patient messages or encyclopedia.
_TIER3_DOCTOR_ANCHOR_RE = re.compile(
    r"^(?:患者|患儿|病人)|主诉[：:]|诊断.{0,2}[：:]|补充[：:]|记录[一下]?[：:]|录入[：:]"
    r"|(?:患者|患儿|病人).{0,5}(?:主诉|诊断|检查|血压|血糖|体温)"
    r"|收入我科|收入我院|门诊以.{0,10}收入"
    # Doctor dictation format: "NAME，gender，age，…"
    # e.g. "李四，女，52岁，反复胸闷" / "王五男58岁冠心病"
    # Patients writing about themselves use first-person ("我" / "我老婆") so this is safe.
    r"|^[\u4e00-\u9fff]{2,3}[，,\s]*[男女](?:性)?[，,\s]*\d+岁"
    # Clinical action phrases — exclusively doctor language.
    # "给予X" = "administer X" (doctor orders treatment, never patient self-report)
    # "建议观察/随访/…" = "recommend …" (doctor assessment sign-off)
    # "排除X病/症/…" = "rule out X" (doctor differential diagnosis)
    r"|给予[\u4e00-\u9fffe-zA-Z]"
    r"|建议(?:观察|随访|复查|门诊|住院|手术|化疗|保守)"
    r"|排除[\u4e00-\u9fff]{1,8}(?:炎|症|癌|瘤|病|塞|梗|折)"
)

# Exam-specific question endings — ALWAYS block, even when doctor anchor is present.
# These endings are exclusive to medical exam MCQs and never appear at the end of
# real clinical dictation. They handle cases where an exam vignette starts with
# "患者，男，45岁..." (which triggers the doctor anchor) but ends with a question.
# CMExam analysis: 40/200 FPs end with "考虑的是", 9 with "治疗应首选", etc.
_TIER3_EXAM_ENDING_RE = re.compile(
    # "应首先考虑的是" / "考虑的是" — single most common MCQ ending (40/200 FPs)
    r"考虑的是[：:]?\s*$"
    # "其诊断是" / "的诊断是" — diagnosis question
    r"|(?:其|的)诊断(?:应)?是[：:]?\s*$"
    # "的疾病是" / "的症状是" / "的体征是" / "的特点是" / etc.
    r"|的(?:疾病|症状|体征|病因|机制|检查|热型|痰液|表现|证候|治法|改变|类型)是[：:]?\s*$"
    # Endings without 的 prefix (e.g. "胸痛特点是", "死亡原因是", "临床表现是")
    r"|(?:特点|原因|表现|机制|体征|检查|热型)是[：:]?\s*$"
    # "临床表现是" / "常见表现是" / "主要表现是"
    r"|(?:临床|常见|主要)表现是[：:]?\s*$"
    # "可见于" / "可见" / "最常见于" / "多见于" / "常伴有" / "放射至"
    r"|(?:最?常?多?)见于\s*$|可见于?\s*$|常伴有\s*$|并伴有\s*$|放射至\s*$"
    # "治疗应首选" / "首选…是" — treatment choice questions
    r"|治疗应首选\s*$|首选.{0,4}是\s*$"
    # "最有意义的是" / "有意义的是"
    r"|意义的是[：:]?\s*$"
    # High-frequency MCQ endings (CMExam analysis: top remaining FP patterns)
    r"|(?:药物|成药|方剂|措施|方法|方案|类型|证候|证型|治法|病原体)是\s*$"
    r"|(?:并发症|不良反应|适应症|禁忌症|副作用)是\s*$"
    # "应诊断为" / "可能诊断为" — diagnosis question ending
    r"|诊断为\s*$|诊断是\s*$"
    # "其部位在" / "位置在"
    r"|部位在\s*$|位置在\s*$"
    # "浊音界呈" / "叩诊音呈" — physical exam findings question
    r"|(?:界|音)[呈在]\s*$"
    # Broad catch: bare 是/为 at end, with optional trailing colon.
    # Real clinical notes always follow 是/为 with the actual value;
    # MCQ questions omit the answer (or follow with a colon for options).
    r"|是[：:]?\s*$|为[：:]?\s*$"
    # Noun/verb-ending MCQ questions (answer is implicit)
    r"|体位\s*$|出现\s*$"
    r"|宜用\s*$|选用\s*$|宜选\s*$|宜选用\s*$|不宜用\s*$|不应用\s*$"
    # "哪项/哪种/哪个" / "何药/何种" — explicit question words; hard block ignores doctor anchor
    r"|哪种|哪项|哪个|哪类|哪些|何药|何种|何法"
    # Quantity questions ("多少个白细胞", "多少mg")
    r"|多少"
    # "属于$" — "大叶性肺炎属于" (without "的是") and "应首选$" with doctor anchor
    r"|属于\s*$|应首选\s*$"
)


def _is_clinical_tier3(text: str) -> bool:
    """Return True when the message contains a high-confidence clinical keyword
    AND does not appear to be a patient question in lay language.

    Checks both the hardcoded ``_CLINICAL_KW_TIER3`` set and the extra keywords
    loaded from ``config/fast_router_keywords.json``.

    Guards (skip Tier 3 → fall through to LLM):
    - 复查-only signal that looks like a reminder command
    - MCQ exam endings (考虑的是, 可见于, 的疾病是…) — hard block, ignores anchor
    - Colloquial patient question phrases (怎么办, 会不会, 正常吗…)
    - Duration/choice/inquiry question patterns (几天了, 是X还是Y, 有没有…)
    - Question-ending particles (吗, 呢 at sentence end)
    - First-person patient voice (我头晕怎么办…)
    - Online-consultation pediatric context (宝宝, 宝贝, 孩子, 小孩)
    Most guards are bypassed when a doctor-voice anchor is detected
    (患者/患儿…, 主诉：, 诊断：, 补充：…). Exam endings are never bypassed.
    """
    all_kw = _CLINICAL_KW_TIER3 | _EXTRA_KW_TIER3
    if not any(kw in text for kw in all_kw):
        return False

    # Guard: 复查-only + reminder command
    if "复查" in text and _REMINDER_RE.search(text):
        other_kw = all_kw - {"复查"}
        return any(kw in text for kw in other_kw)

    # Guard: MCQ exam endings — hard block, NOT overridden by doctor anchor.
    # Exam vignettes start with "患者，男，N岁..." (triggering doctor anchor) but
    # end with a question stem — we detect and reject them here first.
    if _TIER3_EXAM_ENDING_RE.search(text):
        return False

    # Guard: patient-question / lay-language voice — skip unless doctor anchor present
    if _TIER3_QUESTION_RE.search(text) or _TIER3_PATIENT_VOICE_RE.match(text):
        return bool(_TIER3_DOCTOR_ANCHOR_RE.search(text))

    # Guard: online-consultation pediatric context — skip unless doctor anchor present
    if _TIER3_CONSULT_RE.search(text):
        return bool(_TIER3_DOCTOR_ANCHOR_RE.search(text))

    # If a doctor-voice anchor is present, trust it unconditionally — the message is
    # a clinical note and the classifier would only introduce unnecessary FNs on short
    # dictation that lacks the long-document structure the classifier was trained on.
    if _TIER3_DOCTOR_ANCHOR_RE.search(text):
        return True

    # Final gate: TF-IDF binary classifier distinguishes real clinical notes from
    # hard-floor patient messages (short symptom descriptions, online consultation
    # histories) that keyword/regex rules cannot separate without semantic understanding.
    # Only applied when no doctor anchor is present — those cases are handled above.
    # Falls back to True if the model is not loaded (no performance regression).
    if _TIER3_CLASSIFIER is not None:
        return bool(_TIER3_CLASSIFIER.predict([text])[0])

    return True


def _extract_tier3_demographics(
    text: str,
) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Extract (name, gender, age) from a clinical message, best-effort."""
    name: Optional[str] = None
    m = _TIER3_NAME_RE.match(text)
    if m:
        candidate = m.group(1)
        if candidate not in _TIER3_BAD_NAME:
            name = candidate
    gender, age = _extract_demographics(text)
    return name, gender, age


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

    # ── Tier 0: import_history — bulk/PDF/Word imports bypass LLM entirely ─────
    if stripped.startswith("[PDF:") or stripped.startswith("[Word:"):
        source = "pdf" if stripped.startswith("[PDF:") else "word"
        return IntentResult(intent=Intent.import_history, extra_data={"source": source})
    if any(kw in stripped for kw in _IMPORT_KEYWORDS):
        date_count = len(_IMPORT_DATE_RE.findall(stripped))
        if date_count >= 2:
            return IntentResult(intent=Intent.import_history, extra_data={"source": "text"})
    if len(stripped) > 800 and len(_IMPORT_DATE_RE.findall(stripped)) >= 2:
        return IntentResult(intent=Intent.import_history, extra_data={"source": "text"})

    # ── Tier 1: list_patients ──────────────────────────────────────────────────
    if normed in _LIST_PATIENTS_EXACT or stripped in _LIST_PATIENTS_EXACT:
        return IntentResult(intent=Intent.list_patients)
    if normed in _LIST_PATIENTS_SHORT or stripped in _LIST_PATIENTS_SHORT:
        return IntentResult(intent=Intent.list_patients)
    if _LIST_PATIENTS_FLEX_RE.match(normed) or _LIST_PATIENTS_FLEX_RE.match(stripped):
        return IntentResult(intent=Intent.list_patients)

    # ── Tier 1: list_tasks ────────────────────────────────────────────────────
    if normed in _LIST_TASKS_EXACT or stripped in _LIST_TASKS_EXACT:
        return IntentResult(intent=Intent.list_tasks)
    if normed in _LIST_TASKS_SHORT or stripped in _LIST_TASKS_SHORT:
        return IntentResult(intent=Intent.list_tasks)
    if _LIST_TASKS_FLEX_RE.match(normed) or _LIST_TASKS_FLEX_RE.match(stripped):
        return IntentResult(intent=Intent.list_tasks)

    # ── Tier 2: complete_task (fully deterministic — no LLM needed) ───────────
    for _pat in (_COMPLETE_TASK_A_RE, _COMPLETE_TASK_B_RE, _COMPLETE_TASK_C_RE, _COMPLETE_TASK_D_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            task_id = _parse_task_num(m.group(1))
            return IntentResult(
                intent=Intent.complete_task,
                extra_data={"task_id": task_id},
            )

    # ── Tier 2: cancel_task ──────────────────────────────────────────────────
    for _pat in (_CANCEL_TASK_A_RE, _CANCEL_TASK_B_RE, _CANCEL_TASK_C_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            task_id = _parse_task_num(m.group(1))
            return IntentResult(intent=Intent.cancel_task, extra_data={"task_id": task_id})

    # ── Tier 2: postpone_task ────────────────────────────────────────────────
    for _pat in (_POSTPONE_TASK_RE, _POSTPONE_TASK_B_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            task_id = _parse_task_num(m.group(1))
            delta_days = _time_unit_to_days(m.group(2), m.group(3))
            return IntentResult(
                intent=Intent.postpone_task,
                extra_data={"task_id": task_id, "delta_days": delta_days},
            )

    # ── Tier 2: schedule_follow_up (standalone, no record needed) ────────────
    for _pat in (_FOLLOWUP_WITH_NAME_RE, _FOLLOWUP_LEAD_TIME_RE):
        m = _pat.match(normed) or _pat.match(stripped)
        if m:
            name = m.group(1)
            if name and name not in _NON_NAME_KEYWORDS:
                follow_up_plan = ""
                if m.lastindex and m.lastindex >= 3:
                    n_raw, unit = m.group(2), m.group(3)
                    if n_raw and unit:
                        follow_up_plan = f"{n_raw}{unit}后随访"
                return IntentResult(
                    intent=Intent.schedule_follow_up,
                    patient_name=name,
                    extra_data={"follow_up_plan": follow_up_plan or "下次随访"},
                )
    m = _FOLLOWUP_RELATIVE_RE.match(normed) or _FOLLOWUP_RELATIVE_RE.match(stripped)
    if m:
        name, rel_time = m.group(1), m.group(2)
        if name and name not in _NON_NAME_KEYWORDS:
            return IntentResult(
                intent=Intent.schedule_follow_up,
                patient_name=name,
                extra_data={"follow_up_plan": f"{rel_time}随访"},
            )
    m = _FOLLOWUP_TIME_FIRST_RE.match(normed) or _FOLLOWUP_TIME_FIRST_RE.match(stripped)
    if m:
        n_raw, unit, name = m.group(1), m.group(2), m.group(3)
        if name and name not in _NON_NAME_KEYWORDS:
            return IntentResult(
                intent=Intent.schedule_follow_up,
                patient_name=name,
                extra_data={"follow_up_plan": f"{n_raw}{unit}后随访"},
            )

    # ── Tier 2: export_outpatient_report (卫生部 2010 标准门诊病历) ───────────
    for target in (normed, stripped):
        m = _OUTPATIENT_REPORT_RE.match(target)
        if m:
            name = m.group(1).strip() or None
            return IntentResult(intent=Intent.export_outpatient_report, patient_name=name or None)
    if _OUTPATIENT_REPORT_NONAME_RE.match(normed) or _OUTPATIENT_REPORT_NONAME_RE.match(stripped):
        return IntentResult(intent=Intent.export_outpatient_report)

    # ── Tier 2: export_records ────────────────────────────────────────────────
    for target in (normed, stripped):
        m = _EXPORT_RE.match(target)
        if m:
            name = m.group(1).strip() or None
            return IntentResult(intent=Intent.export_records, patient_name=name or None)
    if _EXPORT_NONAME_RE.match(normed) or _EXPORT_NONAME_RE.match(stripped):
        return IntentResult(intent=Intent.export_records)

    # ── Tier 2: supplement / record continuation → add_record ─────────────────
    # "补充：…", "补一句：…", "加上…" are unambiguously appending to a record.
    if _SUPPLEMENT_RE.match(stripped):
        return IntentResult(intent=Intent.add_record)

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
        m = _CREATE_DUPLICATE_RE.match(target)
        if m and m.group(1) not in _NON_NAME_KEYWORDS:
            name = m.group(1)
            gender, age = _extract_demographics(stripped)
            return IntentResult(
                intent=Intent.create_patient,
                patient_name=name,
                gender=gender,
                age=age,
            )

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

        m = _DELETE_OCCINDEX_RE.match(target)
        if m and m.group(2) not in _NON_NAME_KEYWORDS:
            occurrence = _parse_task_num(m.group(1))
            return IntentResult(
                intent=Intent.delete_patient,
                patient_name=m.group(2),
                extra_data={"occurrence_index": occurrence},
            )

    # ── Tier 2: update_patient_info (demographic correction) ─────────────────
    for target in (normed, stripped):
        m = _UPDATE_PATIENT_DEMO_RE.search(target)
        if m:
            name = m.group(1) or (m.group(2) if m.lastindex and m.lastindex >= 2 else None)
            if name and name not in _NON_NAME_KEYWORDS:
                gender, age = _extract_demographics(stripped)
                return IntentResult(
                    intent=Intent.update_patient,
                    patient_name=name,
                    gender=gender,
                    age=age,
                )

    # ── Tier 2.5: update_record — MUST come before Tier 3 ────────────────────
    # Correction messages often contain clinical keywords (e.g. "胸痛", "STEMI")
    # which would otherwise be caught by Tier 3 and mis-routed as add_record.
    # Detecting correction intent first ensures the update_record handler runs.
    # Field extraction is deliberately left to the LLM (no structured_fields here)
    # so the update_medical_record tool can parse correction phrasing accurately.
    if _CORRECT_RECORD_RE.search(stripped):
        name = None
        # Try correction-specific pattern first: "刚才[NAME]的..." / "上一条[NAME]的..."
        cm = _CORRECT_NAME_RE.search(stripped)
        if cm:
            name = cm.group(1) or (cm.group(2) if cm.lastindex and cm.lastindex >= 2 else None)
            if name in _TIER3_BAD_NAME or name in _NON_NAME_KEYWORDS:
                name = None
        # Fallback: name at message start (less common in correction phrasing)
        if name is None:
            m = _TIER3_NAME_RE.match(stripped)
            if m and m.group(1) not in _TIER3_BAD_NAME:
                name = m.group(1)
        return IntentResult(intent=Intent.update_record, patient_name=name)

    # ── Mined rules (loaded from data/mined_rules.json) ──────────────────────
    for rule in _MINED_RULES:
        if not rule["enabled"]:
            continue
        if len(stripped) < rule.get("min_length", 0):
            continue
        matched = any(p.search(stripped) for p in rule["patterns"])
        if not matched and rule.get("keywords_any"):
            matched = any(k in stripped for k in rule["keywords_any"])
        if matched:
            return IntentResult(intent=Intent[rule["intent"]])

    # ── Tier 3: high-confidence clinical content → add_record ────────────────
    # Skips the routing LLM call entirely; structuring LLM still runs.
    # Conservative: only fires for messages long enough and containing at least
    # one term that is almost exclusively used in clinical contexts.
    if len(stripped) >= 6 and _is_clinical_tier3(stripped):
        name, gender, age = _extract_tier3_demographics(stripped)
        return IntentResult(
            intent=Intent.add_record,
            patient_name=name,
            gender=gender,
            age=age,
        )

    return None


def fast_route_label(text: str) -> str:
    """Return a routing label and record it in routing_metrics."""
    result = fast_route(text)
    label = "llm" if result is None else f"fast:{result.intent.value}"
    from services.observability.routing_metrics import record
    record(label)
    return label


# ── Mined rules ────────────────────────────────────────────────────────────────
# Rules loaded from an external JSON file produced by scripts/mine_routing_rules.py.
# Each rule is applied BEFORE Tier 3 in fast_route().

_MINED_RULES: List[Dict[str, Any]] = []


def load_mined_rules(path: str) -> None:
    """Load mined routing rules from a JSON file.

    The file must be a JSON array of objects with the schema::

        [
          {
            "intent": "add_record",
            "patterns": ["^先记[：:]", "^早班.*记[：:]"],
            "keywords_any": ["先记", "早班记"],
            "min_length": 4,
            "enabled": true
          }
        ]

    Silently skips if the file does not exist.
    """
    global _MINED_RULES
    p = Path(path)
    if not p.exists():
        return
    try:
        raw: List[Dict[str, Any]] = json.loads(p.read_text(encoding="utf-8"))
        compiled: List[Dict[str, Any]] = []
        for rule in raw:
            if not isinstance(rule, dict):
                continue
            intent_name = rule.get("intent", "")
            if intent_name not in Intent.__members__:
                continue
            patterns = [re.compile(pat) for pat in rule.get("patterns", [])]
            compiled.append({
                "intent": intent_name,
                "patterns": patterns,
                "keywords_any": list(rule.get("keywords_any") or []),
                "min_length": int(rule.get("min_length", 0)),
                "enabled": bool(rule.get("enabled", True)),
            })
        _MINED_RULES = compiled
    except Exception:
        pass


def reload_mined_rules(path: str = "data/mined_rules.json") -> int:
    """Hot-reload mined rules from disk.

    Returns the number of rules loaded.
    """
    load_mined_rules(path)
    return len(_MINED_RULES)


# Load rules at module import time (no-op if file absent).
load_mined_rules("data/mined_rules.json")
