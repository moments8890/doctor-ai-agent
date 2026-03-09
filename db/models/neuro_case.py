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
    # Diagnosis classification
    diagnosis_subtype: Optional[str] = None       # ICH|SAH|ischemic|AVM|aneurysm|moyamoya|other
    hemorrhage_location: Optional[str] = None

    # ICH-specific
    ich_score: Optional[int] = None               # 0-6
    ich_volume_ml: Optional[float] = None
    hemorrhage_etiology: Optional[str] = None     # hypertensive|caa|avm|coagulopathy|tumor|unknown

    # SAH grading
    hunt_hess_grade: Optional[int] = None         # 1-5
    fisher_grade: Optional[int] = None            # 1-4 (原始Fisher)
    wfns_grade: Optional[int] = None              # 1-5; WFNS分级，与Hunt-Hess并列
    modified_fisher_grade: Optional[int] = None   # 0-4; 改良Fisher，预测血管痉挛更准

    # SAH post-op monitoring
    vasospasm_status: Optional[str] = None        # none|clinical|radiographic|severe
    nimodipine_regimen: Optional[str] = None      # 尼莫地平方案（途径/剂量/天数）

    # ICH/SAH shared complication
    hydrocephalus_status: Optional[str] = None    # none|acute|chronic|shunt_dependent

    # AVM
    spetzler_martin_grade: Optional[int] = None   # 1-5

    # General severity
    gcs_score: Optional[int] = None               # 3-15

    # Aneurysm details
    aneurysm_location: Optional[str] = None
    aneurysm_size_mm: Optional[float] = None
    aneurysm_neck_width_mm: Optional[float] = None  # 瘤颈宽度，决定手术方式
    aneurysm_morphology: Optional[str] = None     # saccular|fusiform|other
    aneurysm_daughter_sac: Optional[str] = None   # yes|no; 子囊（破裂风险高）
    aneurysm_treatment: Optional[str] = None      # clipping|coiling|pipeline|conservative
    phases_score: Optional[int] = None            # 0-12; 未破裂动脉瘤破裂风险PHASES评分

    # Moyamoya disease
    suzuki_stage: Optional[int] = None            # 1-6; 铃木分期，烟雾病DSA形态学分期
    bypass_type: Optional[str] = None             # direct_sta_mca|indirect_edas|combined|other
    perfusion_status: Optional[str] = None        # normal|mildly_reduced|severely_reduced|improved

    # Surgical decision
    surgery_type: Optional[str] = None
    surgery_date: Optional[str] = None
    surgery_status: Optional[str] = None          # planned|done|cancelled|conservative
    surgical_approach: Optional[str] = None

    # Functional outcome
    mrs_score: Optional[int] = None               # 0-6
    barthel_index: Optional[int] = None           # 0-100

    def has_data(self) -> bool:
        """True if at least one clinical field is non-null."""
        return any(
            getattr(self, f) is not None
            for f in ("diagnosis_subtype", "ich_score", "hunt_hess_grade",
                      "wfns_grade", "fisher_grade", "gcs_score", "spetzler_martin_grade",
                      "vasospasm_status", "hydrocephalus_status", "suzuki_stage",
                      "bypass_type", "phases_score", "aneurysm_location",
                      "surgery_type", "surgery_status", "mrs_score")
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
