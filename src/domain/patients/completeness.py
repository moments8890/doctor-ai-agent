"""Field completeness check and merge logic for interview (ADR 0016)."""
from __future__ import annotations

from typing import Dict, List

# --- Field tiers (shared across modes) ---

REQUIRED = ("chief_complaint", "present_illness")

# 病史 fields — asked of both doctor and patient
SUBJECTIVE_RECOMMENDED = ("past_history", "allergy_history", "family_history", "personal_history")
SUBJECTIVE_OPTIONAL = ("marital_reproductive",)

# 检查 / 诊断 / 处置 — doctor only
OBJECTIVE = ("physical_exam", "specialist_exam", "auxiliary_exam")
ASSESSMENT = ("diagnosis",)
PLAN = ("treatment_plan", "orders_followup")

# Doctor-mode recommended: encourage filling these
DOCTOR_RECOMMENDED = SUBJECTIVE_RECOMMENDED + ("physical_exam", "diagnosis", "treatment_plan")
DOCTOR_OPTIONAL = SUBJECTIVE_OPTIONAL + ("specialist_exam", "auxiliary_exam", "orders_followup")

# Patient-mode: only Subjective fields
PATIENT_ALL = REQUIRED + SUBJECTIVE_RECOMMENDED + SUBJECTIVE_OPTIONAL
PATIENT_TOTAL = len(PATIENT_ALL)  # 7

# Doctor-mode: all 14 clinical record fields
DOCTOR_ALL = REQUIRED + SUBJECTIVE_RECOMMENDED + SUBJECTIVE_OPTIONAL + OBJECTIVE + ASSESSMENT + PLAN
DOCTOR_TOTAL = len(DOCTOR_ALL)  # 14

# All fields that can ever be collected (union)
ALL_COLLECTABLE = DOCTOR_ALL
TOTAL_FIELDS = DOCTOR_TOTAL  # 14

APPENDABLE = frozenset({
    "present_illness", "past_history", "allergy_history",
    "family_history", "personal_history", "marital_reproductive",
    "physical_exam", "specialist_exam", "auxiliary_exam",
    "treatment_plan", "orders_followup",
})


def check_completeness(collected: Dict[str, str], *, mode: str = "patient") -> List[str]:
    """Return list of missing field names. Empty list = ready for review.

    In patient mode: required → then subjective recommended.
    In doctor mode: required → then doctor recommended (includes O/A/P).
    """
    missing = [f for f in REQUIRED if not collected.get(f)]
    if not missing:
        recommended = DOCTOR_RECOMMENDED if mode == "doctor" else SUBJECTIVE_RECOMMENDED
        missing = [f for f in recommended if f not in collected]
    return missing


def count_filled(collected: Dict[str, str], *, mode: str = "patient") -> int:
    """Count how many collectable fields have values."""
    fields = DOCTOR_ALL if mode == "doctor" else PATIENT_ALL
    return sum(1 for f in fields if collected.get(f))


def total_fields(mode: str = "patient") -> int:
    """Total number of fields for the given mode."""
    return DOCTOR_TOTAL if mode == "doctor" else PATIENT_TOTAL


def merge_extracted(collected: Dict[str, str], extracted: Dict[str, str]) -> None:
    """Merge LLM-extracted fields into collected dict. Mutates collected in-place.

    Deduplicates: skips if the new value is already present in existing text.
    """
    for field, value in extracted.items():
        if not value or field not in ALL_COLLECTABLE:
            continue
        value = value.strip()
        if field in APPENDABLE:
            existing = collected.get(field, "")
            if existing and value in existing:
                continue  # already contains this info
            collected[field] = f"{existing}；{value}".strip("；") if existing else value
        else:
            collected[field] = value
