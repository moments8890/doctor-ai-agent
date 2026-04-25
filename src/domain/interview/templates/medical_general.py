"""GeneralMedicalTemplate — Phase 2.5 implementation.

Phase 2.5: GeneralMedicalExtractor now owns the full medical prompt context
building (prompt_partial), metadata extraction (extract_metadata), and reply
softening (post_process_reply). The legacy _call_interview_llm in
interview_turn.py is the behavior reference — byte-identical context output is
the preservation bar.
"""
from __future__ import annotations

from typing import Any

from domain.interview.protocols import (
    BatchExtractor, CompletenessState, EngineConfig, FieldExtractor, FieldSpec,
    Mode, Phase, PersistRef, PostConfirmHook, SessionState, Template, Writer,
)
from domain.patients.interview_context import (
    _load_patient_info,
    _load_previous_history,
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
        session_state: SessionState,
        completeness_state: CompletenessState,
        phase: Phase,
        mode: Mode,
    ) -> list[dict[str, str]]:
        """Build the medical interview LLM message list.

        Phase 2.5: absorbs the patient_context + history-window logic that
        previously lived in _call_interview_llm. The engine passes structured
        state; this method produces the messages list.
        """
        import json

        collected = session_state.collected
        conversation = session_state.conversation
        state = completeness_state

        # Field metadata for hints (from template's own FieldSpec list)
        fields_by_name = {f.name: f for f in self.fields()}

        # Fetch patient info + previous history (medical-specific)
        patient_info = await _load_patient_info(session_state.patient_id)
        previous_history = await _load_previous_history(
            session_state.patient_id, session_state.doctor_id,
        )

        # Clean collected (drop underscore-prefixed metadata)
        clean_collected = {k: v for k, v in collected.items() if not k.startswith("_")}
        can_str = "是" if state.can_complete else "否"

        # "待补充" with inline hints (top 3 recommended/optional fields)
        guide_parts = []
        for fk in (list(state.recommended_missing) + list(state.optional_missing))[:3]:
            spec = fields_by_name.get(fk)
            label = (spec.label if spec else fk) or fk
            if spec and (spec.description or spec.example):
                hint = spec.description or ""
                example = spec.example or ""
                if hint and example:
                    guide_parts.append(f'{label}({hint},如"{example}")')
                elif hint:
                    guide_parts.append(f'{label}({hint})')
                else:
                    guide_parts.append(label)
            else:
                guide_parts.append(label)

        # Required missing (only when can_complete is False)
        req_parts = []
        if not state.can_complete:
            for fk in state.required_missing:
                spec = fields_by_name.get(fk)
                label = (spec.label if spec else fk) or fk
                if spec and (spec.description or spec.example):
                    hint = spec.description or ""
                    example = spec.example or ""
                    if hint and example:
                        req_parts.append(f'{label}({hint},如"{example}")')
                    elif hint:
                        req_parts.append(f'{label}({hint})')
                    else:
                        req_parts.append(label)
                else:
                    req_parts.append(label)

        context_lines = [
            f"患者：{patient_info['name']}，{patient_info['gender']}，{patient_info['age']}岁",
            f"已收集：{json.dumps(clean_collected, ensure_ascii=False)}",
            f"可完成：{can_str}",
        ]
        if req_parts:
            context_lines.append(f"必填缺：{'｜'.join(req_parts)}")
        if guide_parts:
            context_lines.append(f"待补充：{'｜'.join(guide_parts)}")
        if previous_history:
            prev = previous_history.replace("\n", " ").strip()
            if len(prev) > 100:
                prev = prev[:100] + "..."
            context_lines.append(f"上次：{prev}")

        # Conversation history window (last 6 turns); summarize early user turns
        _HISTORY_WINDOW = 6
        if len(conversation) > _HISTORY_WINDOW:
            early_turns = conversation[:-_HISTORY_WINDOW]
            early_summary_parts = []
            for t in early_turns:
                role_label = "患者" if t.get("role") == "user" else "助手"
                content = t.get("content", "").strip()
                if content and role_label == "患者":
                    early_summary_parts.append(content[:80])
            if early_summary_parts:
                context_lines.append(f"早期对话摘要：{'；'.join(early_summary_parts)}")

        patient_context = "\n".join(context_lines)

        history = [
            {"role": turn.get("role", "user"), "content": turn.get("content", "")}
            for turn in conversation[-_HISTORY_WINDOW:]
        ]

        # Separate the latest user message from history (goes to doctor_message slot)
        latest_msg = ""
        prior_history = history
        if history and history[-1].get("role") == "user":
            latest_msg = history[-1]["content"]
            prior_history = history[:-1]

        if mode == "doctor":
            return await _compose_for_doctor_interview(
                doctor_id=session_state.doctor_id,
                patient_context=patient_context,
                doctor_message=latest_msg,
                history=prior_history,
                template_id=session_state.template_id,
            )
        return await _compose_for_patient_interview(
            doctor_id=session_state.doctor_id,
            patient_context=patient_context,
            doctor_message=latest_msg,
            history=prior_history,
            template_id=session_state.template_id,
        )

    def extract_metadata(
        self, extracted: dict[str, str],
    ) -> dict[str, str]:
        """Pop patient metadata out of the raw LLM extraction dict.

        Medical templates surface patient_name/gender/age at the turn level;
        engine stores them as underscore-prefixed keys in session.collected.
        """
        out = {}
        for key in ("patient_name", "patient_gender", "patient_age"):
            value = extracted.get(key)
            if isinstance(value, str):
                value = value.strip()
            if value:
                out[key] = value
        return out

    def post_process_reply(
        self, reply: str, collected: dict[str, str], mode: Mode,
    ) -> str:
        """Soften blocking language when all required fields are set.

        If can_complete=True (required fields filled), rewrite phrases like
        "还需要补充X" → "如方便可再补充" and strip "必须..." / "还缺...".
        Preserves the current interview_turn.py:317-325 behavior.
        """
        import re
        state = self.completeness(collected, mode)
        if not state.can_complete:
            return reply

        # Only soften if reply contains blocking language
        if not any(kw in reply for kw in ("还需要", "必须", "还缺")):
            return reply

        out = re.sub(r"还需要补充.+?[。；]?", "如方便可再补充", reply)
        out = re.sub(r"必须.+?[。；]?", "", out)
        out = re.sub(r"还缺.+?[。；]?", "", out)
        if not out.strip():
            out = "已记录。现在可以点击「完成」生成病历。"
        return out

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
            # Patient interview drives the full pre-consultation loop: all
            # subjective fields are required before the session is "ready
            # to review". This matches patient-interview.md's stop condition.
            required = [s.name for s in specs]
            recommended = []
            optional = []
        else:
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


# Columns that the writer controls explicitly — NOT mapped from `collected`
# even if a key with the same name is present. Keep in sync with the
# explicit kwargs in persist() below.
#
# - id / created_at / updated_at: auto-generated by the ORM.
# - doctor_id / patient_id: sourced from session + _ensure_patient, never
#   from `collected`.
# - record_type / status / content: derived by the writer itself
#   (record_type is fixed, status from completeness heuristics, content
#   from _build_clinical_text).
_WRITER_CONTROLLED_COLUMNS: frozenset[str] = frozenset({
    "id",
    "created_at",
    "updated_at",
    "doctor_id",
    "patient_id",
    "record_type",
    "status",
    "content",
})


class MedicalRecordWriter:
    """Writer. Persists the confirmed interview to medical_records.

    Maps `collected` keys to `MedicalRecordDB` columns generically: any
    `collected` key whose name matches an ORM column (and isn't writer-
    controlled) becomes a kwarg on the INSERT. This lets specialty variants
    (e.g. medical_neuro_v1) introduce new FieldSpec + column pairs without
    the writer caring.

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

        # Dynamic column mapping: any `collected` key that matches an ORM
        # column on MedicalRecordDB and is not writer-controlled flows through
        # as a kwarg. Underscore-prefixed keys (engine-level metadata like
        # _patient_name) are skipped. Unknown keys are silently ignored.
        table_columns = {c.name for c in MedicalRecordDB.__table__.columns}
        column_kwargs = {
            key: value
            for key, value in collected.items()
            if not key.startswith("_")
            and key in table_columns
            and key not in _WRITER_CONTROLLED_COLUMNS
        }

        async with AsyncSessionLocal() as db:
            await _ensure_doctor_exists(db, session.doctor_id)
            record = MedicalRecordDB(
                doctor_id=session.doctor_id,
                patient_id=patient_id,
                record_type="interview_summary",
                status=status,
                content=clinical_text,
                **column_kwargs,
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
