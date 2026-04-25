"""Server-side gate for patient-facing KB items.

A KB item is patient-facing iff BOTH:
  1. The item itself is flagged `patient_safe = True`, AND
  2. The owning doctor has completed `kb_curation_onboarding_done`.

Why both: `patient_safe` defaults to False on every item, but per-item
opt-in alone isn't enough (Codex round 2 pushback). Until the doctor
has walked through their KB and reviewed every item explicitly, no
individual `patient_safe=True` flag is honored. The doctor flag is
set after that walkthrough completes — see `kb_curation_onboarding_done`
on the Doctor model.

This gate is the single point of enforcement; every code path that
considers using a KB item in a patient-facing reply MUST call
`is_patient_safe(item, doctor)`. Greppable by name.
"""
from __future__ import annotations


def is_patient_safe(item, doctor) -> bool:
    """Return True iff the item may be used in a patient-facing reply.

    Defensive against None inputs — never returns True when either side
    of the gate is missing.
    """
    if item is None or doctor is None:
        return False
    return (
        bool(getattr(item, "patient_safe", False))
        and bool(getattr(doctor, "kb_curation_onboarding_done", False))
    )
