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
