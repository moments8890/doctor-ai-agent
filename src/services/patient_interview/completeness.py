"""Field completeness check and merge logic for patient interview (ADR 0016)."""
from __future__ import annotations

from typing import Dict, List

REQUIRED = ("chief_complaint", "present_illness")
ASK_AT_LEAST = ("past_history", "allergy_history", "family_history", "personal_history")
OPTIONAL = ("marital_reproductive",)

ALL_COLLECTABLE = REQUIRED + ASK_AT_LEAST + OPTIONAL
TOTAL_FIELDS = len(ALL_COLLECTABLE)  # 7

APPENDABLE = frozenset({
    "present_illness", "past_history", "allergy_history",
    "family_history", "personal_history", "marital_reproductive",
})


def check_completeness(collected: Dict[str, str]) -> List[str]:
    """Return list of missing field names. Empty list = ready for review."""
    missing = [f for f in REQUIRED if not collected.get(f)]
    if not missing:
        missing = [f for f in ASK_AT_LEAST if f not in collected]
    return missing


def count_filled(collected: Dict[str, str]) -> int:
    """Count how many of the 7 collectable fields have values."""
    return sum(1 for f in ALL_COLLECTABLE if collected.get(f))


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
