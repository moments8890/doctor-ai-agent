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
        description="给医生或患者的自然语言回复（先回应，再提问）",
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

FIELD_META = {
    "chief_complaint": {"hint": "促使就诊的主要症状+持续时间", "example": "腹痛3天", "tier": "required"},
    "present_illness": {"hint": "症状详情、演变、已做检查", "example": "脐周阵发性钝痛，无放射，进食后加重", "tier": "required"},
    "past_history": {"hint": "既往疾病、手术、长期用药", "example": "高血压10年，口服氨氯地平", "tier": "recommended"},
    "allergy_history": {"hint": "药物/食物过敏", "example": "青霉素过敏", "tier": "recommended"},
    "family_history": {"hint": "家族遗传病史", "example": "父亲糖尿病", "tier": "recommended"},
    "personal_history": {"hint": "吸烟、饮酒、职业暴露", "example": "吸烟20年，1包/天", "tier": "recommended"},
    "marital_reproductive": {"hint": "婚育情况", "example": "已婚，育1子", "tier": "optional"},
    "physical_exam": {"hint": "生命体征、阳性/阴性体征", "example": "腹软，脐周压痛，无反跳痛", "tier": "recommended"},
    "specialist_exam": {"hint": "专科特殊检查", "example": "肛门指检未触及肿物", "tier": "optional"},
    "auxiliary_exam": {"hint": "化验、影像结果", "example": "血常规WBC 12.5×10⁹/L", "tier": "optional"},
    "diagnosis": {"hint": "初步诊断或印象", "example": "急性胃肠炎", "tier": "recommended"},
    "treatment_plan": {"hint": "处方、处置、建议", "example": "口服蒙脱石散，清淡饮食", "tier": "recommended"},
    "orders_followup": {"hint": "医嘱及复诊安排", "example": "3天后复诊，如加重急诊", "tier": "optional"},
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
    from domain.patients.completeness import (
        REQUIRED, DOCTOR_RECOMMENDED, DOCTOR_OPTIONAL,
        SUBJECTIVE_RECOMMENDED, SUBJECTIVE_OPTIONAL,
    )

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

    # Grouped completeness counts
    can_complete = all(collected.get(f) for f in REQUIRED)

    if mode == "doctor":
        req_fields = list(REQUIRED)
        rec_fields = [f for f in DOCTOR_RECOMMENDED if f not in REQUIRED]
    else:
        req_fields = list(REQUIRED)
        rec_fields = [f for f in SUBJECTIVE_RECOMMENDED if f not in REQUIRED]

    required_count = sum(1 for f in req_fields if collected.get(f))
    required_total = len(req_fields)
    recommended_count = sum(1 for f in rec_fields if collected.get(f))
    recommended_total = len(rec_fields)

    return {
        "filled": filled,
        "total": total,
        "pct": pct,
        "phase": phase,
        "fields": fields,
        "can_complete": can_complete,
        "required_count": required_count,
        "required_total": required_total,
        "recommended_count": recommended_count,
        "recommended_total": recommended_total,
    }


@dataclass
class InterviewResponse:
    reply: str
    collected: Dict[str, str]
    progress: dict  # structured progress with fields, pct, phase
    status: str
    missing: List[str] = None
    suggestions: List[str] = None
    ready_to_review: bool = False
    patient_name: Optional[str] = None
    patient_gender: Optional[str] = None
    patient_age: Optional[str] = None
