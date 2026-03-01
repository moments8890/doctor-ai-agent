"""Rule-based intent detection using jieba POS tagging + regex.

No LLM call — runs in < 5 ms with zero network dependency.

Intent priority (checked in order):
  1. create_patient  — most specific, explicit patient-creation keywords
  2. query_records   — query/history keywords
  3. add_record      — medical content keywords
  4. unknown         — fallback
"""
import re
import jieba.posseg as pseg
from services.intent import Intent, IntentResult

# ---------------------------------------------------------------------------
# Keyword lists
# ---------------------------------------------------------------------------

_CREATE_KW = [
    "新患者", "建档", "新病人", "建立患者", "添加患者",
    "注册患者", "登记患者", "创建患者", "新建患者",
]

_QUERY_KW = [
    "查询", "查一下", "查看", "历史记录", "病历记录",
    "查病历", "看病历", "历史", "过去记录", "之前记录",
    "查记录", "看看记录", "看看病历",
]

_RECORD_KW = [
    "诊断", "主诉", "治疗", "症状", "病历", "开药",
    "处方", "检查", "化验", "手术", "随访", "复诊",
    "发烧", "发热", "咳嗽", "头痛", "腹痛", "胸闷",
    "血压", "血糖", "心率", "病情", "病史",
]


# ---------------------------------------------------------------------------
# Entity extractors
# ---------------------------------------------------------------------------

def _extract_name(text: str) -> str | None:
    # 1. jieba POS — 'nr' tag = person name
    for word, flag in pseg.cut(text):
        if flag.startswith("nr") and 1 < len(word) <= 4:
            return word

    # 2. Pattern: after 患者/叫/名叫
    m = re.search(r'(?:患者|叫做?|名叫)\s*([^\s，,。！？\d]{2,4})', text)
    if m:
        return m.group(1)

    return None


def _extract_age(text: str) -> int | None:
    m = re.search(r'(\d+)\s*岁', text)
    return int(m.group(1)) if m else None


def _extract_gender(text: str) -> str | None:
    if re.search(r'男(?:性|生|士)?', text):
        return "男"
    if re.search(r'女(?:性|生|士)?', text):
        return "女"
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_intent_rules(text: str) -> IntentResult:
    name   = _extract_name(text)
    age    = _extract_age(text)
    gender = _extract_gender(text)

    if any(kw in text for kw in _CREATE_KW):
        return IntentResult(intent=Intent.create_patient, patient_name=name, age=age, gender=gender)

    if any(kw in text for kw in _QUERY_KW):
        return IntentResult(intent=Intent.query_records, patient_name=name, age=age, gender=gender)

    if any(kw in text for kw in _RECORD_KW):
        return IntentResult(intent=Intent.add_record, patient_name=name, age=age, gender=gender)

    return IntentResult(intent=Intent.unknown)
