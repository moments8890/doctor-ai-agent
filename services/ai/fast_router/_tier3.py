"""
Tier-3 binary classifier and clinical keyword gate for fast_router.

P1: accepts optional specialty parameter for specialty-aware keyword expansion.
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Optional

from ._keywords import _CLINICAL_KW_TIER3, _TIER3_BAD_NAME, _EMERGENCY_KW
from ._patient_guard import _is_patient_question
from ._patterns import _extract_demographics, _TIER3_NAME_RE

# ── Tier-3 binary classifier (TF-IDF + logistic regression) ──────────────────
# Loaded once at import; used as the final gate in _is_clinical_tier3().
# Falls back to True (old behaviour) if the model file is absent — i.e. the
# system works without the classifier, just with the old ~10-19% FP hard floors.
_TIER3_CLASSIFIER = None
_TIER3_CLASSIFIER_PATH = Path(__file__).parent.parent / "tier3_classifier.pkl"


def _load_tier3_classifier() -> None:
    global _TIER3_CLASSIFIER
    if _TIER3_CLASSIFIER_PATH.exists():
        try:
            with _TIER3_CLASSIFIER_PATH.open("rb") as _f:
                _TIER3_CLASSIFIER = pickle.load(_f)
        except Exception:
            _TIER3_CLASSIFIER = None


_load_tier3_classifier()

_REMINDER_RE = re.compile(r"提醒|设.*\d+[点时:：]|设.*复查提醒")

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
    # Follow-up note prefix: "随访：张三…" / "复查，血压稳定…" — doctor write-up only
    r"|^随访[：:,，]"
    r"|^[\u4e00-\u9fff]{2,3}(?:复查|随访)[，,]"
    # Blood pressure reading in doctor note: "120/80" — lay patients don't write this way
    r"|\d{2,3}/\d{2,3}"
)

# Stronger anchor used only when a question pattern was already detected.
# Excludes the bare "^患者/病人" prefix because patients can write "患者头痛怎么办？"
# referring to themselves. Requires an unambiguously clinical signal.
_TIER3_STRONG_DOCTOR_ANCHOR_RE = re.compile(
    r"主诉[：:]|诊断.{0,2}[：:]|补充[：:]|记录[一下]?[：:]|录入[：:]"
    r"|(?:患者|患儿|病人).{0,5}(?:主诉|诊断|检查|血压|血糖|体温)"
    r"|收入我科|收入我院|门诊以.{0,10}收入"
    r"|^[\u4e00-\u9fff]{2,3}[，,\s]*[男女](?:性)?[，,\s]*\d+岁"
    r"|给予[\u4e00-\u9fffe-zA-Z]"
    r"|建议(?:观察|随访|复查|门诊|住院|手术|化疗|保守)"
    r"|排除[\u4e00-\u9fff]{1,8}(?:炎|症|癌|瘤|病|塞|梗|折)"
    r"|^随访[：:,，]"
    r"|^[\u4e00-\u9fff]{2,3}(?:复查|随访)[，,]"
    r"|\d{2,3}/\d{2,3}"
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


def _is_clinical_tier3(text: str, specialty: Optional[str] = None) -> bool:
    """Return True when the message contains a high-confidence clinical keyword
    AND does not appear to be a patient question in lay language.

    Uses the static ``_CLINICAL_KW_TIER3`` frozenset compiled into the module.

    P1: ``specialty`` parameter is reserved for future specialty-aware keyword
    expansion; currently unused.

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
    # P1: specialty parameter reserved for future specialty-aware expansion
    all_kw = _CLINICAL_KW_TIER3

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

    # Guard: patient-question / lay-language voice — skip unless STRONG doctor anchor.
    # Uses _TIER3_STRONG_DOCTOR_ANCHOR_RE (excludes bare "患者" prefix) because
    # patients can write "患者头痛怎么办？" referring to themselves.
    if _is_patient_question(text) or _TIER3_PATIENT_VOICE_RE.match(text):
        return bool(_TIER3_STRONG_DOCTOR_ANCHOR_RE.search(text))

    # Guard: online-consultation pediatric context — skip unless strong doctor anchor
    if _TIER3_CONSULT_RE.search(text):
        return bool(_TIER3_STRONG_DOCTOR_ANCHOR_RE.search(text))

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
