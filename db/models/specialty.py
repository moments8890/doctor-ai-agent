"""
专科临床上下文表：卒中、癫痫、帕金森、痴呆、头痛。
每张表与 medical_records 和 patients 关联，存储该专科的结构化临床字段。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.engine import Base
from db.models.base import _utcnow


class StrokeClinicalContext(Base):
    __tablename__ = "stroke_clinical_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    onset_datetime: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    thrombolysis_eligible: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    thrombolysis_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # recommended|contraindicated|done|not_indicated
    toast_classification: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # LAA|SVO|CE|UND|OTH
    target_sbp_mmhg: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    antiplatelet_agent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    anticoag_agent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_stroke_context_doctor_patient", "doctor_id", "patient_id"),
    )


class EpilepsyClinicalContext(Base):
    __tablename__ = "epilepsy_clinical_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    seizure_frequency_per_month: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_seizure_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    breakthrough_seizure: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    breakthrough_triggers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of trigger strings
    aed_medications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON [{"drug":"lamictal","dose":"100mg","frequency":"bid"}]
    eeg_result: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_epilepsy_context_doctor_patient", "doctor_id", "patient_id"),
    )


class ParkinsonClinicalContext(Base):
    __tablename__ = "parkinson_clinical_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    hoehn_yahr_stage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 1.0 to 5.0
    levodopa_equivalent_dose: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # mg/day
    on_off_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # on|off|fluctuating
    dyskinesia_present: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    dopamine_agonist: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_parkinson_context_doctor_patient", "doctor_id", "patient_id"),
    )


class DementiaClinicalContext(Base):
    __tablename__ = "dementia_clinical_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    mmse_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    moca_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cdr_stage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0, 0.5, 1, 2, 3
    adl_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cognitive_domains_affected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_dementia_context_doctor_patient", "doctor_id", "patient_id"),
    )


class HeadacheClinicalContext(Base):
    __tablename__ = "headache_clinical_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)
    attack_frequency_per_month: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attack_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attack_triggers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    acute_medication: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    preventive_medication: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_headache_context_doctor_patient", "doctor_id", "patient_id"),
    )


class NeuroCVDContext(Base):
    """神经外科脑血管疾病专病临床上下文：每条病历对应一行结构化字段。"""
    __tablename__ = "neuro_cvd_context"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(Integer, ForeignKey("medical_records.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    doctor_id: Mapped[str] = mapped_column(String(64), ForeignKey("doctors.doctor_id", ondelete="CASCADE"), nullable=False)

    # Diagnosis classification
    diagnosis_subtype: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # ICH|SAH|ischemic|AVM|aneurysm|other
    hemorrhage_location: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 出血部位

    # ICH-specific
    ich_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)               # 0-6
    ich_volume_ml: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # SAH / aneurysm grading
    hunt_hess_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)         # 1-5
    fisher_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)            # 1-4

    # AVM
    spetzler_martin_grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 1-5

    # General severity
    gcs_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)               # 3-15

    # Aneurysm details
    aneurysm_location: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    aneurysm_size_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    aneurysm_morphology: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # saccular|fusiform|other
    aneurysm_treatment: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)   # clipping|coiling|pipeline|conservative

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
