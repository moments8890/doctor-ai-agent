"""
共享 PDF 辅助工具：字体解析、日期格式化、字体设置闭包等。

被 pdf_records.py 和 pdf_outpatient.py 共同引用。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Section → structured-field mapping (for filtered PDF export)
# ---------------------------------------------------------------------------

VALID_SECTIONS = {"basic", "diagnosis", "visits", "prescriptions", "allergies"}

_SECTION_FIELDS: dict[str, list[str]] = {
    "diagnosis": ["diagnosis", "final_diagnosis", "key_symptoms"],
    "visits": [
        "chief_complaint", "present_illness", "past_history",
        "physical_exam", "specialist_exam", "auxiliary_exam",
        "treatment_plan", "orders_followup",
    ],
    "prescriptions": ["orders_followup"],
    "allergies": ["allergy_history"],
}

# Chinese labels for structured fields rendered in the filtered PDF
_FIELD_LABELS: dict[str, str] = {
    "diagnosis": "初步诊断",
    "final_diagnosis": "最终诊断",
    "key_symptoms": "关键症状",
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "physical_exam": "体格检查",
    "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查",
    "treatment_plan": "治疗方案",
    "orders_followup": "医嘱及随访",
    "allergy_history": "过敏史",
}


def _allowed_fields(sections: Optional[set]) -> Optional[set]:
    """Return the union of fields for the requested sections, or None (= all)."""
    if sections is None:
        return None
    fields: set = set()
    for sec in sections:
        fields.update(_SECTION_FIELDS.get(sec, []))
    return fields


# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------

_CANDIDATE_FONTS = [
    "/System/Library/Fonts/STHeiti Light.ttc",           # macOS
    "/System/Library/Fonts/PingFang.ttc",                # macOS (newer)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Ubuntu
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Ubuntu alt
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # Ubuntu WQY
    "/Library/Fonts/Arial Unicode.ttf",                  # macOS fallback
]


def _resolve_font_path() -> Optional[str]:
    env_path = os.environ.get("PDF_FONT_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path
    for p in _CANDIDATE_FONTS:
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_RISK_LABEL = {
    "critical": "极高危",
    "high": "高危",
    "medium": "中危",
    "low": "低危",
}


def _record_type_label(record_type: str) -> str:
    mapping = {
        "visit": "门诊",
        "dictation": "口述",
        "import": "导入",
        "interview_summary": "问诊总结",
    }
    return mapping.get(record_type or "visit", record_type or "门诊")


def _fmt_datetime(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


def _age_from_year(year_of_birth: Optional[int]) -> Optional[int]:
    if not year_of_birth:
        return None
    return datetime.now().year - int(year_of_birth)


def _make_set_font(pdf, has_cjk: bool):
    """返回闭包，按 CJK 可用情况设置字体。"""
    def _set_font(size: int, bold: bool = False):
        if has_cjk:
            pdf.set_font("CJK", size=size)
        else:
            style = "B" if bold else ""
            pdf.set_font("Helvetica", style=style, size=size)
    return _set_font
