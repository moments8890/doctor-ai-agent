"""medical_neuro_v1 — 神外 cerebrovascular variant.

Phase 4 r2 — Task 3: extractor + field list. Task 8: template binding
(GeneralNeuroTemplate) + TEMPLATES registration.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from domain.interview.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)
from domain.interview.hooks.safety import SafetyScreenHook
from domain.interview.protocols import (
    BatchExtractor, CompletenessState, EngineConfig, FieldExtractor, FieldSpec,
    Mode, Phase, PostConfirmHook, SessionState, Writer,
)
from domain.interview.templates.medical_general import (
    GeneralMedicalExtractor, MEDICAL_FIELDS, MedicalBatchExtractor,
    MedicalRecordWriter,
)

# Neuro extends the patient-mode subjective-field subset with `onset_time`
# because the thrombolysis window matters before the patient even reaches
# a doctor — the patient side intake must require it.
_NEURO_PATIENT_EXTRA_FIELDS: frozenset[str] = frozenset({"onset_time"})

# ---- field specs — neuro extras on top of MEDICAL_FIELDS -------------------

NEURO_EXTRA_FIELDS: list[FieldSpec] = [
    FieldSpec(name="onset_time", type="string", tier="required", appendable=False,
              label="发病时间",
              description="症状首次出现的时间（绝对时间或相对现在的小时数）",
              example="今晨7:30，约2小时前"),
    FieldSpec(name="neuro_exam", type="text", tier="recommended", appendable=True,
              label="神经系统查体",
              description="GCS、瞳孔、肌力、反射、脑神经、病理征",
              example="GCS 15，双侧瞳孔等大等圆，左上肢肌力3级，巴氏征（+）"),
    FieldSpec(name="vascular_risk_factors", type="text", tier="recommended",
              appendable=True, carry_forward_modes=frozenset({"doctor"}),
              label="血管危险因素",
              description="高血压/糖尿病/房颤/吸烟/家族卒中史",
              example="高血压10年，房颤，吸烟20年"),
]

NEURO_FIELDS: list[FieldSpec] = [*MEDICAL_FIELDS, *NEURO_EXTRA_FIELDS]


_NEURO_GUIDANCE = (
    "【神外重点】本次问诊为神经外科（脑血管方向），重点关注："
    "(1) 发病时间（溶栓窗）；(2) 神经系统查体（GCS/肌力/瞳孔/脑神经/病理征）；"
    "(3) 血管危险因素（高血压/糖尿病/房颤/吸烟/家族史）；"
    "(4) 危险信号：突发剧烈头痛、意识障碍、单侧肢体无力、言语不清、视物改变、呕吐、抽搐。"
    "若任一危险信号出现，立即提示就医。"
)


class GeneralNeuroExtractor(GeneralMedicalExtractor):
    """Neuro variant. Overrides fields() and injects neuro guidance into
    the prompt partial. All merge/completeness/extract-metadata/
    post-process behavior inherited unchanged — the extra FieldSpec entries
    participate in the shared FieldSpec-driven logic.
    """

    def fields(self) -> list[FieldSpec]:
        return NEURO_FIELDS

    async def prompt_partial(
        self,
        session_state: SessionState,
        completeness_state: CompletenessState,
        phase: Phase,
        mode: Mode,
    ) -> list[dict[str, str]]:
        messages = await super().prompt_partial(
            session_state, completeness_state, phase, mode,
        )
        if messages and messages[0].get("role") == "system":
            messages[0] = {
                **messages[0],
                "content": messages[0]["content"] + "\n\n" + _NEURO_GUIDANCE,
            }
        return messages

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState:
        """Neuro completeness. Same tier semantics as the parent, but the
        patient-mode subjective subset is widened to include `onset_time`
        (thrombolysis window; patient must volunteer it before review).
        """
        specs = self.fields()

        # Keep in sync with GeneralMedicalExtractor.completeness._PATIENT_FIELDS;
        # extended here with neuro-specific patient-subject fields.
        _PATIENT_FIELDS = {
            "chief_complaint", "present_illness", "past_history",
            "allergy_history", "family_history", "personal_history",
            "marital_reproductive",
        } | _NEURO_PATIENT_EXTRA_FIELDS

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


# ---- template binding -------------------------------------------------------


@dataclass
class GeneralNeuroTemplate:
    id: str = "medical_neuro_v1"
    kind: str = "medical"
    display_name: str = "神外问诊（脑血管）"
    requires_doctor_review: bool = True
    supported_modes: tuple[Mode, ...] = ("patient", "doctor")
    extractor: FieldExtractor = field(default_factory=GeneralNeuroExtractor)
    batch_extractor: BatchExtractor | None = field(
        default_factory=MedicalBatchExtractor,
    )
    writer: Writer = field(default_factory=MedicalRecordWriter)
    post_confirm_hooks: dict[Mode, list[PostConfirmHook]] = field(
        default_factory=lambda: {
            "patient": [
                TriggerDiagnosisPipelineHook(),
                NotifyDoctorHook(),
                SafetyScreenHook(),
            ],
            "doctor": [
                GenerateFollowupTasksHook(),
                SafetyScreenHook(),
            ],
        }
    )
    config: EngineConfig = field(default_factory=lambda: EngineConfig(
        max_turns=30,
        phases={"patient": ["default"], "doctor": ["default"]},
    ))
