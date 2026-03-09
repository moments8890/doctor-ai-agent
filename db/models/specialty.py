"""
神经外科脑血管疾病专病临床上下文表。
每张表与 medical_records 和 patients 关联，存储结构化临床字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class NeuroCVDContext(Base):
    """神经外科脑血管疾病专病临床上下文：每条病历对应一行结构化字段。"""
    __tablename__ = "neuro_cvd_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)

    # Diagnosis classification
    diagnosis_subtype: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # ICH|SAH|ischemic|AVM|aneurysm|moyamoya|other
    hemorrhage_location: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # ICH-specific
    ich_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)               # 0-6
    ich_volume_ml: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hemorrhage_etiology: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # hypertensive|caa|avm|coagulopathy|tumor|unknown

    # SAH grading
    hunt_hess_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)         # 1-5
    fisher_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)            # 1-4
    wfns_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)              # 1-5; WFNS分级
    modified_fisher_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 0-4; 改良Fisher

    # SAH post-op monitoring
    vasospasm_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)     # none|clinical|radiographic|severe
    nimodipine_regimen: Mapped[Optional[str]] = mapped_column(Text, nullable=True)         # 尼莫地平方案

    # ICH/SAH shared complication
    hydrocephalus_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True) # none|acute|chronic|shunt_dependent

    # AVM
    spetzler_martin_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 1-5

    # General severity
    gcs_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)               # 3-15

    # Aneurysm details
    aneurysm_location: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    aneurysm_size_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    aneurysm_neck_width_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 瘤颈宽度mm
    aneurysm_morphology: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # saccular|fusiform|other
    aneurysm_daughter_sac: Mapped[Optional[str]] = mapped_column(String(8), nullable=True) # yes|no
    aneurysm_treatment: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # clipping|coiling|pipeline|conservative
    phases_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)            # 0-12; PHASES评分

    # Moyamoya disease
    suzuki_stage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)            # 1-6; 铃木分期
    bypass_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)          # direct_sta_mca|indirect_edas|combined|other
    perfusion_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)     # normal|mildly_reduced|severely_reduced|improved

    # Surgical decision
    surgery_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    surgery_date: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)         # YYYY-MM-DD
    surgery_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)       # planned|done|cancelled|conservative
    surgical_approach: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Functional outcome
    mrs_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)               # 0-6
    barthel_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)           # 0-100

    source: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)               # chat|voice|import
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_neuro_cvd_doctor_patient", "doctor_id", "patient_id"),
        Index("ix_neuro_cvd_patient_ts", "patient_id", "created_at"),
    )
