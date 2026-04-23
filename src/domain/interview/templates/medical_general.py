"""GeneralMedicalTemplate — Phase 1 thin-stub implementation.

Every method delegates to pre-Phase-1 codepaths. Phase 2 inlines the logic
here and deletes the legacy sources. Phase 1 keeps the legacy sources live.
"""
from __future__ import annotations

from typing import Any

from domain.interview.protocols import (
    BatchExtractor, CompletenessState, EngineConfig, FieldExtractor, FieldSpec,
    Mode, Phase, PersistRef, PostConfirmHook, SessionState, Template, Writer,
)

# ---- field specs — canonical source of medical-interview schema ------------

# Declarative: add/remove/reorder fields here. Legacy callers import via the
# completeness.py and interview_models.py shims (both now thin re-exports).

MEDICAL_FIELDS: list[FieldSpec] = [
    FieldSpec(
        name="chief_complaint", type="string", tier="required", appendable=False,
        label="主诉",
        description="促使就诊的主要症状+持续时间",
        example="腹痛3天",
    ),
    FieldSpec(
        name="present_illness", type="text", tier="required", appendable=True,
        label="现病史",
        description="症状详情、演变、已做检查",
        example="脐周阵发性钝痛，无放射，进食后加重",
    ),
    FieldSpec(
        name="past_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="既往史",
        description="既往疾病、手术、长期用药",
        example="高血压10年，口服氨氯地平",
    ),
    FieldSpec(
        name="allergy_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="过敏史",
        description="药物/食物过敏",
        example="青霉素过敏",
    ),
    FieldSpec(
        name="family_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="家族史",
        description="家族遗传病史",
        example="父亲糖尿病",
    ),
    FieldSpec(
        name="personal_history", type="text", tier="recommended", appendable=True,
        carry_forward_modes=frozenset({"doctor"}),
        label="个人史",
        description="吸烟、饮酒、职业暴露",
        example="吸烟20年，1包/天",
    ),
    FieldSpec(
        name="marital_reproductive", type="text", tier="optional", appendable=True,
        label="婚育史",
        description="婚育情况",
        example="已婚，育1子",
    ),
    FieldSpec(
        name="physical_exam", type="text", tier="recommended", appendable=True,
        label="体格检查",
        description="生命体征、阳性/阴性体征",
        example="腹软，脐周压痛，无反跳痛",
    ),
    FieldSpec(
        name="specialist_exam", type="text", tier="optional", appendable=True,
        label="专科检查",
        description="专科特殊检查",
        example="肛门指检未触及肿物",
    ),
    FieldSpec(
        name="auxiliary_exam", type="text", tier="optional", appendable=True,
        label="辅助检查",
        description="化验、影像结果",
        example="血常规WBC 12.5×10⁹/L",
    ),
    FieldSpec(
        name="diagnosis", type="string", tier="recommended", appendable=False,
        label="诊断",
        description="初步诊断或印象",
        example="急性胃肠炎",
    ),
    FieldSpec(
        name="treatment_plan", type="text", tier="recommended", appendable=True,
        label="治疗方案",
        description="处方、处置、建议",
        example="口服蒙脱石散，清淡饮食",
    ),
    FieldSpec(
        name="orders_followup", type="text", tier="optional", appendable=True,
        label="医嘱及随访",
        description="医嘱及复诊安排",
        example="3天后复诊，如加重急诊",
    ),
    FieldSpec(
        name="department", type="string", tier="optional", appendable=False,
        label="科别",
        description="科别：门诊/急诊/住院 + 科室",
    ),
]


# ---- extractor -------------------------------------------------------------

from agent.prompt_composer import (
    compose_for_doctor_interview as _compose_for_doctor_interview,
    compose_for_patient_interview as _compose_for_patient_interview,
)


class GeneralMedicalExtractor:
    """Phase 1 thin-stub FieldExtractor. Every method forwards to legacy code."""

    def fields(self) -> list[FieldSpec]:
        return MEDICAL_FIELDS

    async def prompt_partial(
        self,
        collected: dict[str, str],
        history: list[dict[str, Any]],
        phase: Phase,
        mode: Mode,
        *,
        doctor_id: str = "",
        patient_context: str = "",
        doctor_message: str = "",
    ) -> list[dict[str, str]]:
        """Compose the intent-layer prompt via prompt_composer.

        Phase 2: accepts explicit doctor_id/patient_context/doctor_message.
        """
        if mode == "doctor":
            return await _compose_for_doctor_interview(
                doctor_id=doctor_id,
                patient_context=patient_context,
                doctor_message=doctor_message,
                history=history,
                template_id="medical_general_v1",
            )
        return await _compose_for_patient_interview(
            doctor_id=doctor_id,
            patient_context=patient_context,
            doctor_message=doctor_message,
            history=history,
            template_id="medical_general_v1",
        )

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]:
        """Merge LLM-extracted fields into collected using FieldSpec.appendable.

        Inlined from completeness.merge_extracted (Phase 2). Dedup rule:
        on appendable fields, if the new value is a substring of existing
        text, skip it. Non-appendable fields always overwrite.
        """
        _fields_by_name = {f.name: f for f in self.fields()}
        for name, value in extracted.items():
            spec = _fields_by_name.get(name)
            if spec is None:
                continue
            if not value:
                continue
            value = value.strip()
            if not value:
                continue
            if spec.appendable:
                existing = collected.get(name, "")
                if existing and value in existing:
                    continue
                collected[name] = (
                    f"{existing}；{value}".strip("；") if existing else value
                )
            else:
                collected[name] = value
        return collected

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState:
        """Tier-based completeness. Uses FieldSpec.tier; patient mode filters
        to the subjective-field subset.

        Inlined from completeness.get_completeness_state (Phase 2).
        """
        specs = self.fields()

        _PATIENT_FIELDS = {
            "chief_complaint", "present_illness", "past_history",
            "allergy_history", "family_history", "personal_history",
            "marital_reproductive",
        }

        if mode == "patient":
            specs = [s for s in specs if s.name in _PATIENT_FIELDS]

        required = [s.name for s in specs if s.tier == "required"]
        recommended = [s.name for s in specs if s.tier == "recommended"]
        optional = [s.name for s in specs if s.tier == "optional"]

        required_missing = [f for f in required if not collected.get(f)]
        recommended_missing = [f for f in recommended if not collected.get(f)]
        optional_missing = [f for f in optional if not collected.get(f)]

        next_focus: str | None = None
        if recommended_missing:
            next_focus = recommended_missing[0]
        elif optional_missing:
            next_focus = optional_missing[0]

        return CompletenessState(
            can_complete=len(required_missing) == 0,
            required_missing=required_missing,
            recommended_missing=recommended_missing,
            optional_missing=optional_missing,
            next_focus=next_focus,
        )

    def next_phase(
        self, session: SessionState, phases: list[Phase],
    ) -> Phase:
        # Phase 1: template declares a single phase. This returns it.
        # Phase 3+ may introduce real branching; keep the protocol ready for that.
        return phases[0]


# ---- batch extractor -------------------------------------------------------


class MedicalBatchExtractor:
    """Phase 1 stub. Forwards to the existing batch_extract_from_transcript."""

    async def extract(
        self,
        conversation: list[dict[str, Any]],
        context: dict[str, Any],
        mode: Mode,
    ) -> dict[str, str] | None:
        # Lazy import to avoid circular dependency:
        # completeness (shim) → medical_general → interview_summary → completeness
        from domain.patients.interview_summary import (
            batch_extract_from_transcript as _batch_extract_from_transcript,
        )
        return await _batch_extract_from_transcript(
            conversation, context, mode=mode,
        )


# ---- writer -----------------------------------------------------------------

from fastapi import HTTPException

from agent.tools.resolve import resolve as _resolve_patient
from db.crud.doctor import _ensure_doctor_exists
from db.engine import AsyncSessionLocal
from db.models.records import MedicalRecordDB, RecordStatus


class MedicalRecordWriter:
    """Phase 1 writer. Persists the confirmed interview to medical_records.

    Absorbs deferred patient creation from confirm.py:72-101. Does NOT fire
    diagnosis / notifications / task generation — those are separate hooks.
    """

    async def persist(
        self, session: SessionState, collected: dict[str, str],
    ) -> PersistRef:
        # Lazy import to avoid circular dependency:
        # completeness (shim) → medical_general → shared → interview_turn → completeness
        from channels.web.doctor_interview.shared import _build_clinical_text

        patient_id = await self._ensure_patient(session, collected)

        clinical_text = _build_clinical_text(collected)
        has_diagnosis = bool(collected.get("diagnosis", "").strip())
        has_treatment = bool(collected.get("treatment_plan", "").strip())
        has_followup = bool(collected.get("orders_followup", "").strip())
        status = (
            RecordStatus.completed.value
            if (has_diagnosis and has_treatment and has_followup)
            else RecordStatus.pending_review.value
        )

        async with AsyncSessionLocal() as db:
            await _ensure_doctor_exists(db, session.doctor_id)
            record = MedicalRecordDB(
                doctor_id=session.doctor_id,
                patient_id=patient_id,
                record_type="interview_summary",
                status=status,
                content=clinical_text,
                chief_complaint=collected.get("chief_complaint"),
                present_illness=collected.get("present_illness"),
                past_history=collected.get("past_history"),
                allergy_history=collected.get("allergy_history"),
                personal_history=collected.get("personal_history"),
                marital_reproductive=collected.get("marital_reproductive"),
                family_history=collected.get("family_history"),
                physical_exam=collected.get("physical_exam"),
                specialist_exam=collected.get("specialist_exam"),
                auxiliary_exam=collected.get("auxiliary_exam"),
                diagnosis=collected.get("diagnosis"),
                treatment_plan=collected.get("treatment_plan"),
                orders_followup=collected.get("orders_followup"),
            )
            db.add(record)
            await db.commit()
            record_id = record.id

        return PersistRef(kind="medical_record", id=record_id)

    async def _ensure_patient(
        self, session: SessionState, collected: dict[str, str],
    ) -> int:
        """If session.patient_id is set, return it. Otherwise resolve from
        collected["_patient_name"] and create the patient row. Mirrors the
        confirm.py:72-101 behavior byte-for-byte."""
        if session.patient_id is not None:
            return session.patient_id

        name = (collected.get("_patient_name") or "").strip()
        if not name:
            raise HTTPException(
                status_code=422,
                detail="无法确认：未检测到患者姓名，请在对话中提供",
            )

        gender = collected.get("_patient_gender")
        age_str = collected.get("_patient_age")
        age: int | None = None
        if age_str:
            try:
                age = int(age_str.rstrip("岁"))
            except (ValueError, AttributeError):
                pass

        resolved = await _resolve_patient(
            name, session.doctor_id, auto_create=True,
            gender=gender, age=age,
        )
        if "status" in resolved:
            raise HTTPException(
                status_code=422,
                detail=resolved.get("message", "Patient creation failed"),
            )
        return resolved["patient_id"]


# ---- template binding -------------------------------------------------------

from dataclasses import dataclass, field

from domain.interview.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)


@dataclass
class GeneralMedicalTemplate:
    """medical_general_v1. Binds all the medical-specific components."""
    id: str = "medical_general_v1"
    kind: str = "medical"
    display_name: str = "通用医学问诊"
    requires_doctor_review: bool = True
    supported_modes: tuple[Mode, ...] = ("patient", "doctor")
    extractor: FieldExtractor = field(default_factory=GeneralMedicalExtractor)
    batch_extractor: BatchExtractor | None = field(default_factory=MedicalBatchExtractor)
    writer: Writer = field(default_factory=MedicalRecordWriter)
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]] = field(
        default_factory=lambda: {
            "patient": [
                TriggerDiagnosisPipelineHook(),
                NotifyDoctorHook(),
            ],
            # §8 open question — doctor-mode is deliberately NOT firing
            # diagnosis in Phase 1 because that matches today's confirm.py.
            # Phase 4 revisits.
            "doctor": [
                GenerateFollowupTasksHook(),
            ],
        }
    )
    config: EngineConfig = field(default_factory=lambda: EngineConfig(
        max_turns=30,
        phases={"patient": ["default"], "doctor": ["default"]},
    ))
