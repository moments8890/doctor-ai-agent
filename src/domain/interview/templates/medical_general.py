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
