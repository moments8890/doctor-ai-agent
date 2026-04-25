"""Deterministic extraction_confidence — count of required history fields filled / 7.

Replaces LLM self-reported confidence (Codex round 2 pushback in the
chat-interview merge spec). The denominator (7) is the number of
required history fields in MedicalRecordDB. Doctor-facing display
shows this as N/7, not as a percentage, so the meaning is
unambiguous (and there's no temptation to interpret a 0.71 as "AI
is 71% sure" — it just means 5 of 7 fields are populated).
"""

REQUIRED_FIELDS = (
    "chief_complaint",
    "present_illness",
    "past_history",
    "allergy_history",
    "personal_history",
    "marital_reproductive",
    "family_history",
)


def calculate(fields: dict[str, str | None]) -> float:
    """Return filled-field ratio in [0.0, 1.0].

    A field counts as filled iff its value is not None and stripping
    whitespace leaves a non-empty string. Fields not in REQUIRED_FIELDS
    are ignored (the input dict may contain extras like `diagnosis`).
    """
    filled = sum(
        1 for f in REQUIRED_FIELDS
        if fields.get(f) is not None and str(fields.get(f)).strip()
    )
    return filled / len(REQUIRED_FIELDS)
