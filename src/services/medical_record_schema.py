"""
OutpatientRecord schema — shared data contract for medical record import/export.

14 fields per 《病历书写基本规范》(卫医政发〔2010〕11号) outpatient record standard.
Used by both export (LLM extraction → JSON/PDF) and import (Vision LLM → record).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class PatientInfo(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None


class OutpatientRecord(BaseModel):
    """门诊病历标准格式 — 14 fields per 《病历书写基本规范》"""

    patient: PatientInfo = Field(default_factory=PatientInfo)

    department: Optional[str] = None           # 科别
    chief_complaint: Optional[str] = None      # 主诉
    present_illness: Optional[str] = None      # 现病史
    past_history: Optional[str] = None         # 既往史
    allergy_history: Optional[str] = None      # 过敏史
    personal_history: Optional[str] = None     # 个人史
    marital_reproductive: Optional[str] = None  # 婚育史
    family_history: Optional[str] = None       # 家族史
    physical_exam: Optional[str] = None        # 体格检查
    specialist_exam: Optional[str] = None      # 专科检查
    auxiliary_exam: Optional[str] = None       # 辅助检查
    diagnosis: Optional[str] = None            # 初步诊断
    treatment_plan: Optional[str] = None       # 治疗方案
    orders_followup: Optional[str] = None      # 医嘱及随访


# Field metadata: (key, chinese_label) — single source of truth for field ordering
OUTPATIENT_FIELD_META: List[Tuple[str, str]] = [
    ("department",           "科别"),
    ("chief_complaint",      "主诉"),
    ("present_illness",      "现病史"),
    ("past_history",         "既往史"),
    ("allergy_history",      "过敏史"),
    ("personal_history",     "个人史"),
    ("marital_reproductive", "婚育史"),
    ("family_history",       "家族史"),
    ("physical_exam",        "体格检查"),
    ("specialist_exam",      "专科检查"),
    ("auxiliary_exam",       "辅助检查"),
    ("diagnosis",            "初步诊断"),
    ("treatment_plan",       "治疗方案"),
    ("orders_followup",      "医嘱及随访"),
]

FIELD_KEYS: List[str] = [k for k, _ in OUTPATIENT_FIELD_META]
