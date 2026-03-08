"""
神经专科病例 Pydantic 模型：定义脑卒中、癫痫等神经科病例的结构化字段。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class Hypertension(BaseModel):
    has_htn: Optional[str] = None       # yes/no/unknown
    years: Optional[int] = None
    control_status: Optional[str] = None


class RiskFactors(BaseModel):
    hypertension: Optional[Hypertension] = None
    diabetes: Optional[str] = None
    hyperlipidemia: Optional[str] = None
    smoking: Optional[str] = None
    drinking: Optional[str] = None
    family_history_cvd: Optional[str] = None


class ImagingFinding(BaseModel):
    vessel: Optional[str] = None
    lesion_type: Optional[str] = None   # stenosis/occlusion/aneurysm/moyamoya/other
    severity_percent: Optional[float] = None
    side: Optional[str] = None
    collateral: Optional[str] = None
    notes: Optional[str] = None


class ImagingStudy(BaseModel):
    modality: str
    datetime: Optional[str] = None
    summary: str
    findings: List[ImagingFinding] = []


class LabResult(BaseModel):
    name: str
    datetime: Optional[str] = None
    result: Optional[str] = None
    unit: Optional[str] = None
    flag: Optional[str] = None          # high/low/normal/unknown
    source_text: str


class PlanOrder(BaseModel):
    type: str                            # lab/imaging/medication/procedure/consult/followup/other
    name: str
    frequency: Optional[str] = None
    notes: Optional[str] = None


class ExtractionLog(BaseModel):
    missing_fields: List[str] = []
    ambiguities: List[str] = []
    normalization_notes: List[str] = []
    confidence_by_module: Dict[str, float] = {}


class NeuroCVDSurgicalContext(BaseModel):
    """结构化的神经外科脑血管疾病专科字段，从 LLM 提取后存入 neuro_cvd_context 表。"""
    diagnosis_subtype: Optional[str] = None       # ICH|SAH|ischemic|AVM|aneurysm|other
    hemorrhage_location: Optional[str] = None
    ich_score: Optional[int] = None
    ich_volume_ml: Optional[float] = None
    hunt_hess_grade: Optional[int] = None
    fisher_grade: Optional[int] = None
    spetzler_martin_grade: Optional[int] = None
    gcs_score: Optional[int] = None
    aneurysm_location: Optional[str] = None
    aneurysm_size_mm: Optional[float] = None
    aneurysm_morphology: Optional[str] = None     # saccular|fusiform|other
    aneurysm_treatment: Optional[str] = None      # clipping|coiling|pipeline|conservative
    surgery_type: Optional[str] = None
    surgery_date: Optional[str] = None
    surgery_status: Optional[str] = None          # planned|done|cancelled|conservative
    surgical_approach: Optional[str] = None
    mrs_score: Optional[int] = None
    barthel_index: Optional[int] = None

    def has_data(self) -> bool:
        """True if at least one clinical field is non-null."""
        return any(
            getattr(self, f) is not None
            for f in ("diagnosis_subtype", "ich_score", "hunt_hess_grade",
                      "fisher_grade", "gcs_score", "spetzler_martin_grade",
                      "aneurysm_location", "surgery_type", "mrs_score")
        )


class NeuroCase(BaseModel):
    case_id: Optional[str] = None
    patient_profile: Dict[str, object] = {}
    encounter: Dict[str, object] = {}
    chief_complaint: Dict[str, object] = {}
    hpi: Dict[str, object] = {}
    past_history: Dict[str, object] = {}
    risk_factors: Optional[RiskFactors] = None
    physical_exam: Dict[str, object] = {}
    neuro_exam: Dict[str, object] = {}
    imaging: List[ImagingStudy] = []
    labs: List[LabResult] = []
    diagnosis: Dict[str, object] = {}
    plan: Dict[str, object] = {}
    provenance: Dict[str, object] = {}
