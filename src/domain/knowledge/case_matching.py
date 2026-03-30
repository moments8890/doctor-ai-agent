"""Case memory — find similar confirmed cases from the doctor's history.

Uses weighted asymmetric coverage over medical_records with confirmed
ai_suggestions. The doctor's confirmed decisions become searchable
for future similar patients.

Matching fields (by weight):
  diagnosis / final_diagnosis  → highest signal
  auxiliary_exam               → imaging findings discriminate well in neurosurgery
  key_symptoms                 → structured symptom tags
  chief_complaint              → standard matching
  present_illness              → narrative detail
"""

import re
from typing import List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.records import MedicalRecordDB
from db.models.ai_suggestion import AISuggestion
from utils.log import log


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(r'[，。、；：！？\s,.:;!?\n\t()（）【】\[\]]+')

# General stop words — keep negation (无/未/不) and laterality (左/右)
# because they carry meaning in medical context.
_STOP_WORDS = {
    "的", "了", "是", "在", "有", "和", "与", "及", "等", "或",
    "可", "为", "被", "将", "把", "从", "到", "对", "于", "以",
    "之", "其", "个", "月", "年", "日", "也", "都", "就", "而",
    "但", "如", "若", "所", "这", "那", "它", "你", "我", "他",
}

# Medical high-frequency but low-signal words
_MEDICAL_STOP_WORDS = {
    "患者", "病人", "目前", "情况", "方面", "建议", "考虑",
    "进行", "需要", "可能", "暂时", "明显", "相关", "提示",
    "表现", "发现", "出现", "开始", "影响", "导致",
}

_ALL_STOP = _STOP_WORDS | _MEDICAL_STOP_WORDS

# Medical terms jieba often splits wrong — loaded once
_MEDICAL_TERMS = [
    "脑膜瘤", "胶质瘤", "胶质母细胞瘤", "听神经瘤", "垂体瘤",
    "动脉瘤", "动静脉畸形", "脑出血", "脑梗死", "蛛网膜下腔出血",
    "颈动脉狭窄", "颈内动脉", "大脑中动脉", "大脑前动脉", "基底动脉",
    "椎动脉", "后交通动脉", "前交通动脉", "海绵窦",
    "桥小脑角", "小脑幕", "颅底", "额叶", "颞叶", "顶叶", "枕叶",
    "基底节", "丘脑", "脑干", "小脑", "脊髓",
    "去骨瓣减压", "颅骨修补", "介入栓塞", "开颅手术", "伽马刀",
    "脑室引流", "腰椎穿刺",
    "高血压", "糖尿病", "房颤", "冠心病", "肾功能不全",
    "抗凝", "抗血小板", "双抗", "华法林", "丙戊酸",
    "Hunt-Hess", "Fisher", "Spetzler-Martin", "NIHSS", "GCS", "mRS",
    "MRI", "MRA", "CTA", "DSA", "CT", "EEG",
]
_JIEBA_LOADED = False


def _ensure_jieba():
    """Load jieba with medical dictionary terms (once)."""
    global _JIEBA_LOADED
    if _JIEBA_LOADED:
        return
    try:
        import jieba
        for term in _MEDICAL_TERMS:
            jieba.add_word(term)
        _JIEBA_LOADED = True
    except ImportError:
        pass


def _tokenize_medical(text: str) -> set:
    """Extract meaningful medical tokens from Chinese clinical text."""
    if not text:
        return set()
    _ensure_jieba()
    try:
        import jieba
        tokens = set()
        for chunk in _SPLIT_RE.split(text):
            chunk = chunk.strip()
            if not chunk:
                continue
            for word in jieba.cut(chunk):
                word = word.strip()
                if len(word) >= 2 and word not in _ALL_STOP:
                    tokens.add(word)
        return tokens
    except ImportError:
        tokens = set()
        for chunk in _SPLIT_RE.split(text):
            chunk = chunk.strip()
            if len(chunk) >= 2 and chunk not in _ALL_STOP:
                tokens.add(chunk)
        return tokens


# ---------------------------------------------------------------------------
# Similarity — weighted asymmetric coverage
# ---------------------------------------------------------------------------

# Fields used for matching, with weights.
# Higher weight = more discriminative for case similarity.
_MATCH_FIELDS = {
    "diagnosis":        3.0,
    "final_diagnosis":  3.0,
    "auxiliary_exam":   2.5,
    "key_symptoms":     2.0,
    "chief_complaint":  1.5,
    "present_illness":  1.0,
}


def _build_weighted_tokens(record_dict: Dict[str, str]) -> Dict[str, float]:
    """Build token→max_weight map from multiple record fields."""
    token_weights: Dict[str, float] = {}
    for field, weight in _MATCH_FIELDS.items():
        text = record_dict.get(field, "") or ""
        if not text:
            continue
        for tok in _tokenize_medical(text):
            if tok not in token_weights or weight > token_weights[tok]:
                token_weights[tok] = weight
    return token_weights


def _compute_similarity(query_weights: Dict[str, float], case_weights: Dict[str, float]) -> float:
    """Weighted asymmetric coverage: how well does the case cover the query?

    score = sum(weight[t] for t in intersection) / sum(weight[t] for t in query)

    Biased toward the query side — a case that covers all query terms scores
    high even if it has many extra tokens.
    """
    if not query_weights:
        return 0.0
    query_total = sum(query_weights.values())
    if query_total == 0:
        return 0.0
    covered = sum(query_weights[t] for t in query_weights if t in case_weights)
    return covered / query_total


# ---------------------------------------------------------------------------
# Main query
# ---------------------------------------------------------------------------

async def find_similar_cases(
    session: AsyncSession,
    doctor_id: str,
    chief_complaint: str,
    present_illness: str = "",
    structured: Dict[str, str] = None,
    limit: int = 3,
    min_similarity: float = 0.15,
) -> List[Dict[str, Any]]:
    """Find similar confirmed cases from the doctor's history.

    Uses weighted asymmetric coverage across multiple record fields.
    Returns top N matches with similarity scores and confirmed decisions.
    """
    # Build query tokens from current patient — use all available fields
    query_dict = {"chief_complaint": chief_complaint, "present_illness": present_illness}
    if structured:
        for field in _MATCH_FIELDS:
            if field in structured and structured[field]:
                query_dict[field] = structured[field]
    query_weights = _build_weighted_tokens(query_dict)

    if not query_weights:
        return []

    # Find records with confirmed decisions by this doctor, ordered by recency
    stmt = (
        select(MedicalRecordDB)
        .join(AISuggestion, AISuggestion.record_id == MedicalRecordDB.id)
        .where(
            AISuggestion.doctor_id == doctor_id,
            AISuggestion.decision.in_(["confirmed", "edited"]),
        )
        .distinct()
        .order_by(MedicalRecordDB.created_at.desc())
        .limit(100)
    )

    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return []

    # Score each record
    scored = []
    for record in rows:
        case_dict = {
            "chief_complaint": record.chief_complaint or "",
            "present_illness": record.present_illness or "",
            "diagnosis": record.diagnosis or "",
            "final_diagnosis": record.final_diagnosis or "",
            "auxiliary_exam": record.auxiliary_exam or "",
            "key_symptoms": record.key_symptoms or "",
        }
        case_weights = _build_weighted_tokens(case_dict)
        sim = _compute_similarity(query_weights, case_weights)
        if sim >= min_similarity:
            scored.append((sim, record))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    # Fetch confirmed decisions for matched records — single query, ordered
    record_ids = [r.id for _, r in top]
    sug_stmt = (
        select(AISuggestion)
        .where(
            AISuggestion.record_id.in_(record_ids),
            AISuggestion.doctor_id == doctor_id,
            AISuggestion.decision.in_(["confirmed", "edited"]),
        )
        .order_by(AISuggestion.record_id, AISuggestion.section, AISuggestion.id)
    )
    all_suggestions = (await session.execute(sug_stmt)).scalars().all()

    # Group suggestions by record_id
    sug_by_record: Dict[int, List[AISuggestion]] = {}
    for s in all_suggestions:
        sug_by_record.setdefault(s.record_id, []).append(s)

    results = []
    for sim, record in top:
        suggestions = sug_by_record.get(record.id, [])

        # Use record.final_diagnosis if available, else build from differential suggestions
        final_diag = record.final_diagnosis or ""
        if not final_diag:
            diff_sugs = [s for s in suggestions if s.section == "differential"]
            final_diag = ", ".join(
                (s.edited_text or s.content) for s in diff_sugs[:3] if s.content
            )[:120]

        # Get treatment from treatment suggestions
        treatment = ""
        for s in suggestions:
            if s.section == "treatment" and s.content:
                treatment = (s.edited_text or s.content)[:100]
                break

        results.append({
            "record_id": record.id,
            "similarity": round(sim, 2),
            "chief_complaint": (record.chief_complaint or "")[:60],
            "final_diagnosis": final_diag or "已确认",
            "treatment": treatment,
            "outcome": record.treatment_outcome or "",
            "patient_id": record.patient_id,
        })

    log(f"[case_matching] found {len(results)} similar cases for doctor {doctor_id}")
    return results
