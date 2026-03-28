"""Interview Pydantic models, field metadata, and progress builder (ADR 0016)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

MAX_TURNS = 30


class ExtractedClinicalFields(BaseModel):
    """Clinical fields extracted from this turn. Only include fields with NEW information."""
    patient_name: Optional[str] = Field(None, description="患者姓名")
    patient_gender: Optional[str] = Field(None, description="患者性别（男/女）")
    patient_age: Optional[str] = Field(None, description="患者年龄")
    department: Optional[str] = Field(None, description="科别：门诊/急诊/住院 + 科室")
    chief_complaint: Optional[str] = Field(None, description="主诉：主要症状+持续时间")
    present_illness: Optional[str] = Field(None, description="现病史：症状详情、检查结果、用药")
    past_history: Optional[str] = Field(None, description="既往史：既往疾病、手术")
    allergy_history: Optional[str] = Field(None, description="过敏史（无过敏填'无'）")
    family_history: Optional[str] = Field(None, description="家族史（无填'无'）")
    personal_history: Optional[str] = Field(None, description="个人史：吸烟、饮酒")
    marital_reproductive: Optional[str] = Field(None, description="婚育史")
    physical_exam: Optional[str] = Field(None, description="体格检查")
    specialist_exam: Optional[str] = Field(None, description="专科检查")
    auxiliary_exam: Optional[str] = Field(None, description="辅助检查：化验、影像")
    diagnosis: Optional[str] = Field(None, description="诊断")
    treatment_plan: Optional[str] = Field(None, description="治疗方案")
    orders_followup: Optional[str] = Field(None, description="医嘱及随访")


class InterviewLLMResponse(BaseModel):
    """Structured response from the interview LLM."""

    reply: str = Field(
        default="请继续描述您的情况。",
        description="给患者的自然语言回复（先回应，再提问）",
    )
    extracted: ExtractedClinicalFields = Field(
        default_factory=ExtractedClinicalFields,
        description="本轮新提取的病历字段（只填有新信息的字段，其余留null）",
    )
    suggestions: List[str] = Field(
        default_factory=list, description="建议的快捷回复选项"
    )


FIELD_LABELS = {
    "chief_complaint": "主诉",
    "present_illness": "现病史",
    "past_history": "既往史",
    "allergy_history": "过敏史",
    "family_history": "家族史",
    "personal_history": "个人史",
    "marital_reproductive": "婚育史",
    "physical_exam": "体格检查",
    "specialist_exam": "专科检查",
    "auxiliary_exam": "辅助检查",
    "diagnosis": "诊断",
    "treatment_plan": "治疗方案",
    "orders_followup": "医嘱及随访",
}


# NHC Article 13 outpatient field priorities
_FIELD_PRIORITY = {
    "chief_complaint": "required",
    "present_illness": "required",
    "past_history": "recommended",
    "allergy_history": "recommended",
    "family_history": "recommended",
    "personal_history": "recommended",
    "marital_reproductive": "optional",
    "physical_exam": "recommended",
    "specialist_exam": "optional",
    "auxiliary_exam": "optional",
    "diagnosis": "recommended",
    "treatment_plan": "recommended",
    "orders_followup": "optional",
}

_PATIENT_PHASES = [
    ("主诉与现病史", ["chief_complaint", "present_illness"]),
    ("病史采集", ["past_history", "allergy_history", "family_history", "personal_history"]),
    ("补充信息", ["marital_reproductive"]),
]


def _build_progress(collected: Dict[str, str], mode: str = "patient") -> dict:
    """Build structured progress metadata for UI rendering."""
    _PATIENT_FIELDS = {
        "chief_complaint", "present_illness", "past_history",
        "allergy_history", "family_history", "personal_history", "marital_reproductive",
    }
    fields = {}
    for key, priority in _FIELD_PRIORITY.items():
        # Patient mode: only show the 7 subjective fields
        if mode == "patient" and key not in _PATIENT_FIELDS:
            continue
        fields[key] = {
            "status": "filled" if collected.get(key) else "empty",
            "priority": priority,
            "label": FIELD_LABELS.get(key, key),
        }

    filled = sum(1 for f in fields.values() if f["status"] == "filled")
    total = len(fields)
    pct = int(round(filled / total * 100)) if total else 0

    # Determine current phase (patient mode only)
    phase = "完成"
    if mode == "patient":
        for phase_name, phase_fields in _PATIENT_PHASES:
            if any(not collected.get(f) for f in phase_fields):
                phase = phase_name
                break

    return {
        "filled": filled,
        "total": total,
        "pct": pct,
        "phase": phase,
        "fields": fields,
    }


@dataclass
class InterviewResponse:
    reply: str
    collected: Dict[str, str]
    progress: dict  # structured progress with fields, pct, phase
    status: str
    missing: List[str] = None
    suggestions: List[str] = None
    patient_name: Optional[str] = None
    patient_gender: Optional[str] = None
    patient_age: Optional[str] = None
