"""
CVD 量表补录面谈：病历确认后自动询问缺失的关键专科量表。

每次病历确认只问 1 个最关键字段，不打扰正常流程。
医生直接回复数字（或「跳过」）即可完成录入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Per subtype: the single most critical missing field to ask about
_SUBTYPE_PRIORITY_FIELD: dict[str, str] = {
    "ICH":      "ich_score",
    "SAH":      "hunt_hess_grade",
    "AVM":      "spetzler_martin_grade",
    "aneurysm": "phases_score",
    "moyamoya": "suzuki_stage",
    "ischemic": "mrs_score",
}

_FIELD_LABELS: dict[str, str] = {
    "ich_score":            "ICH Score",
    "hunt_hess_grade":      "Hunt-Hess 分级",
    "fisher_grade":         "Fisher 分级",
    "spetzler_martin_grade": "Spetzler-Martin 分级",
    "phases_score":         "PHASES Score",
    "suzuki_stage":         "铃木分期",
    "mrs_score":            "mRS 评分",
    "gcs_score":            "GCS 评分",
}

_QUESTIONS: dict[str, str] = {
    "ich_score": (
        "🧠 请补充 ICH Score（0–6分）：\n"
        "年龄≥80岁+1，血肿量≥30ml+1，幕下出血+1，脑室扩展+1，GCS 3-4分+2，GCS 5-12分+1\n"
        "直接回复数字，或「跳过」"
    ),
    "hunt_hess_grade": (
        "🧠 请补充 Hunt-Hess 分级（1–5级）：\n"
        "1=轻头痛/无症状，2=中重度头痛/颈强，3=嗜睡/局灶缺损，4=昏迷/重度偏瘫，5=深昏迷/去脑强直\n"
        "直接回复数字，或「跳过」"
    ),
    "spetzler_martin_grade": (
        "🧠 请补充 Spetzler-Martin 分级（1–5分）：\n"
        "大小（<3cm=1，3-6cm=2，>6cm=3）+ 位置（非功能区=0，功能区=1）+ 引流静脉（浅=0，深=1）\n"
        "直接回复总分，或「跳过」"
    ),
    "phases_score": (
        "🧠 请补充 PHASES Score（0–12分，未破裂动脉瘤破裂风险）：\n"
        "直接回复数字，或「跳过」"
    ),
    "suzuki_stage": (
        "🧠 请补充铃木分期（1–6期）：\n"
        "1=颈内动脉末端狭窄，6=颈内动脉完全闭塞/侧支消失\n"
        "直接回复数字，或「跳过」"
    ),
    "mrs_score": (
        "🧠 请补充 mRS 评分（0–6分）：\n"
        "0=无症状，1=无明显残疾，2=轻度残疾，3=中度残疾，4=重度残疾，5=重度残疾需护理，6=死亡\n"
        "直接回复数字，或「跳过」"
    ),
}

# Ordered list of (subtype, keyword_list) for subtype detection from text
_SUBTYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("SAH",      ["蛛网膜下腔", "SAH", "Hunt-Hess", "Fisher", "破裂动脉瘤", "脑血管痉挛", "尼莫地平"]),
    ("ICH",      ["脑出血", "颅内出血", "ICH", "血肿", "基底节出血", "丘脑出血", "脑室出血", "壳核"]),
    ("AVM",      ["AVM", "动静脉畸形", "Spetzler"]),
    ("aneurysm", ["动脉瘤", "PHASES", "未破裂", "夹闭", "栓塞", "Pipeline"]),
    ("moyamoya", ["烟雾病", "moyamoya", "铃木", "Suzuki", "搭桥"]),
    ("ischemic", ["脑梗", "缺血性卒中", "取栓", "溶栓", "tPA", "NIHSS", "TOAST", "血管内治疗"]),
]

_SKIP_WORDS = frozenset({"跳过", "skip", "不知道", "不清楚", "无", "没有", "n/a", "na"})


def detect_cvd_subtype(text: str) -> Optional[str]:
    """Keyword-based CVD subtype detection. Returns the first match."""
    for subtype, keywords in _SUBTYPE_KEYWORDS:
        if any(kw in text for kw in keywords):
            return subtype
    return None


@dataclass
class CVDScaleSession:
    record_id: int
    patient_id: Optional[int]
    field_name: str    # DB column on neuro_cvd_context
    subtype: str

    def question(self) -> str:
        return _QUESTIONS.get(self.field_name, f"🧠 请补充 {_FIELD_LABELS.get(self.field_name, self.field_name)}：")

    def field_label(self) -> str:
        return _FIELD_LABELS.get(self.field_name, self.field_name)

    def parse_answer(self, text: str) -> Optional[int]:
        """Return integer score or None (skip/invalid)."""
        stripped = text.strip().lower()
        if stripped in _SKIP_WORDS:
            return None
        try:
            return int(stripped)
        except ValueError:
            m = re.search(r"\d+", stripped)
            return int(m.group()) if m else None


def build_cvd_scale_session(
    record_id: int,
    patient_id: Optional[int],
    record_content: str,
    cvd_raw: Optional[dict] = None,
) -> Optional[CVDScaleSession]:
    """Return CVDScaleSession if the record has CVD content and the priority scale is missing."""
    subtype = None
    if cvd_raw:
        subtype = cvd_raw.get("diagnosis_subtype")
    if not subtype:
        subtype = detect_cvd_subtype(record_content)
    if not subtype:
        return None

    priority_field = _SUBTYPE_PRIORITY_FIELD.get(subtype)
    if not priority_field:
        return None

    # Skip if agent already extracted this field
    if cvd_raw and cvd_raw.get(priority_field) is not None:
        return None

    return CVDScaleSession(
        record_id=record_id,
        patient_id=patient_id,
        field_name=priority_field,
        subtype=subtype,
    )
