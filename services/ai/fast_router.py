"""
基于关键词、正则和临床启发式规则的快速意图路由，无需调用 LLM，90% 以上的指令在 1ms 内响应。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.ai.intent import Intent, IntentResult

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
_SUPPLEMENT_RE = re.compile(
    r"^(?:补充[：:。\s]|补一句[：:。\s]?|再补充|加上.{0,8}[，,]?|追加[：:]"
    r"|(?:好[，,]?\s*)?写进去[。！]?$)"
)

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
_TIER3_QUESTION_RE = re.compile(
    r"怎么办|怎么回事|是怎么回事|该怎么|是什么原因|有什么办法|有什么方法"
    r"|怎么治疗|如何治疗|会不会|能不能|吃什么药|是什么病"
    r"|有什么关系|正常吗|严重吗|有没有问题|是否严重"
)

# First-person patient voice: "我…怎么办", "我家宝宝…", etc.
_TIER3_PATIENT_VOICE_RE = re.compile(
    r"^(?:我|我家|我妈|我爸|我爷|我奶|我老|我儿|我女|我孩|我宝|我老婆|我丈夫|我先生)"
    r".{0,30}(?:怎么|是否|会不会|能不能|为什么|什么原因|[？?])"
)

# Doctor-voice anchor: overrides the question guards when present.
# A doctor may include a question within a clinical note.
_TIER3_DOCTOR_ANCHOR_RE = re.compile(
    r"^(?:患者|病人)|主诉[：:]|诊断[：:]|补充[：:]|记录[一下]?[：:]|录入[：:]"
    r"|(?:患者|病人).{0,5}(?:主诉|诊断|检查|血压|血糖|体温)"
)


def _is_clinical_tier3(text: str) -> bool:
    """Return True when the message contains a high-confidence clinical keyword
    AND does not appear to be a patient question in lay language.

    Checks both the hardcoded ``_CLINICAL_KW_TIER3`` set and the extra keywords
    loaded from ``config/fast_router_keywords.json``.

    Guards (skip Tier 3 → fall through to LLM):
    - 复查-only signal that looks like a reminder command
    - Colloquial patient question phrases (怎么办, 会不会, 正常吗…)
    - First-person patient voice (我头晕怎么办…)
    These guards are bypassed when a doctor-voice anchor is detected
    (患者…, 主诉：, 诊断：, 补充：…).
    """
    all_kw = _CLINICAL_KW_TIER3 | _EXTRA_KW_TIER3
    if not any(kw in text for kw in all_kw):
        return False

    # Guard: 复查-only + reminder command
    if "复查" in text and _REMINDER_RE.search(text):
        other_kw = all_kw - {"复查"}
        return any(kw in text for kw in other_kw)

    # Guard: patient-question / lay-language voice — skip unless doctor anchor present
    if _TIER3_QUESTION_RE.search(text) or _TIER3_PATIENT_VOICE_RE.match(text):
        return bool(_TIER3_DOCTOR_ANCHOR_RE.search(text))

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
