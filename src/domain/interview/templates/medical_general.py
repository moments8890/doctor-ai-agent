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

# ---- field specs ------------------------------------------------------------

from domain.patients.completeness import APPENDABLE, REQUIRED
from domain.patients.interview_models import FIELD_LABELS, FIELD_META
from channels.web.doctor_interview.shared import _CARRY_FORWARD_FIELDS


def _build_medical_fields() -> list[FieldSpec]:
    """Translate the existing scattered metadata into a single FieldSpec list.

    Order follows FIELD_LABELS insertion order, with `department` appended
    afterward (it exists on ExtractedClinicalFields but has no FIELD_LABELS
    entry).  Each field's attributes are derived from the live source constants:
    - tier   = "required" if in REQUIRED else "recommended" if in
               DOCTOR_RECOMMENDED else "optional"
    - label  = FIELD_LABELS[name] if present, else field description from
               ExtractedClinicalFields
    - description = FIELD_META[name]["hint"] if present, else label
    - example = FIELD_META[name]["example"] if present
    - appendable = name in APPENDABLE
    - carry_forward_modes = frozenset({"doctor"}) if name in _CARRY_FORWARD_FIELDS
                            else frozenset()
    """
    from domain.patients.completeness import DOCTOR_RECOMMENDED
    from domain.patients.interview_models import ExtractedClinicalFields

    # Build the set of non-patient pydantic fields that have no FIELD_LABELS entry
    # (currently just "department") so we can add specs for them too.
    pydantic_no_label = {
        n for n in ExtractedClinicalFields.model_fields.keys()
        if not n.startswith("patient_") and n not in FIELD_LABELS
    }

    # Derive pydantic field descriptions as a fallback label source
    pydantic_descriptions = {
        n: (field.description or n)
        for n, field in ExtractedClinicalFields.model_fields.items()
    }

    specs: list[FieldSpec] = []

    # Primary loop: iterate FIELD_LABELS insertion order
    for name, label in FIELD_LABELS.items():
        meta = FIELD_META.get(name, {})
        hint = meta.get("hint") or label
        example = meta.get("example")

        if name in REQUIRED:
            tier = "required"
        elif name in DOCTOR_RECOMMENDED:
            tier = "recommended"
        else:
            tier = "optional"

        specs.append(FieldSpec(
            name=name,
            type="text" if name in APPENDABLE else "string",
            description=hint,
            example=example,
            label=label,
            tier=tier,
            appendable=(name in APPENDABLE),
            carry_forward_modes=(
                frozenset({"doctor"}) if name in _CARRY_FORWARD_FIELDS
                else frozenset()
            ),
        ))

    # Secondary loop: pydantic fields not covered by FIELD_LABELS (e.g. department)
    for name in sorted(pydantic_no_label):
        meta = FIELD_META.get(name, {})
        hint = meta.get("hint") or pydantic_descriptions.get(name, name)
        example = meta.get("example")

        if name in REQUIRED:
            tier = "required"
        elif name in DOCTOR_RECOMMENDED:
            tier = "recommended"
        else:
            tier = "optional"

        specs.append(FieldSpec(
            name=name,
            type="text" if name in APPENDABLE else "string",
            description=hint,
            example=example,
            label=pydantic_descriptions.get(name, name),
            tier=tier,
            appendable=(name in APPENDABLE),
            carry_forward_modes=(
                frozenset({"doctor"}) if name in _CARRY_FORWARD_FIELDS
                else frozenset()
            ),
        ))

    return specs


MEDICAL_FIELDS: list[FieldSpec] = _build_medical_fields()


# ---- extractor -------------------------------------------------------------

from domain.patients.completeness import (
    get_completeness_state as _get_completeness_state,
    merge_extracted as _merge_extracted,
)
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
    ) -> list[dict[str, str]]:
        """Forward to the existing prompt composer. Phase 2 will absorb the
        intent-layer prompt loading into the extractor; Phase 1 preserves
        the current composition exactly."""
        if mode == "doctor":
            return await _compose_for_doctor_interview(**_composer_kwargs(
                collected, history, phase, mode,
            ))
        return await _compose_for_patient_interview(**_composer_kwargs(
            collected, history, phase, mode,
        ))

    def merge(
        self, collected: dict[str, str], extracted: dict[str, str],
    ) -> dict[str, str]:
        _merge_extracted(collected, extracted)
        return collected

    def completeness(
        self, collected: dict[str, str], mode: Mode,
    ) -> CompletenessState:
        raw = _get_completeness_state(collected, mode=mode)
        return CompletenessState(
            can_complete=raw["can_complete"],
            required_missing=raw["required_missing"],
            recommended_missing=raw["recommended_missing"],
            optional_missing=raw["optional_missing"],
            next_focus=raw["next_focus"],
        )

    def next_phase(
        self, session: SessionState, phases: list[Phase],
    ) -> Phase:
        # Phase 1: template declares a single phase. This returns it.
        # Phase 3+ may introduce real branching; keep the protocol ready for that.
        return phases[0]


def _composer_kwargs(
    collected: dict[str, str],
    history: list[dict[str, Any]],
    phase: Phase,
    mode: Mode,
) -> dict[str, Any]:
    """Minimal kwargs the composer needs. The engine passes the full
    context via SessionState at call time (Task 10); this helper is the
    current no-op stub used during unit-level tests where Task 10 hasn't
    wired the real kwargs yet."""
    return {
        "doctor_id": "",
        "patient_context": "",
        "doctor_message": "",
        "history": history,
        "template_id": "medical_general_v1",
    }


# ---- batch extractor -------------------------------------------------------

from domain.patients.interview_summary import (
    batch_extract_from_transcript as _batch_extract_from_transcript,
)


class MedicalBatchExtractor:
    """Phase 1 stub. Forwards to the existing batch_extract_from_transcript."""

    async def extract(
        self,
        conversation: list[dict[str, Any]],
        context: dict[str, Any],
        mode: Mode,
    ) -> dict[str, str] | None:
        return await _batch_extract_from_transcript(
            conversation, context, mode=mode,
        )


# ---- writer -----------------------------------------------------------------

from fastapi import HTTPException

from agent.tools.resolve import resolve as _resolve_patient
from channels.web.doctor_interview.shared import _build_clinical_text
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
