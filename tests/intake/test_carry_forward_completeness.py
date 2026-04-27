"""Carry-forward fields must be patient-confirmed before counting as filled.

Regression: an intake bootstrapped with carry-forward seeded all 5 phase-2
fields (past/allergy/family/personal/marital) from the previous record. The
completeness check treated those values as filled, so after turn 2 (only
chief_complaint + present_illness extracted) the engine flipped to
``reviewing`` and emitted the wrap-up reply. Patient was never asked about
any of the carried fields.

Fix: ``GeneralMedicalExtractor.completeness`` now consults
``_carry_forward_meta[field].confirmed_by_patient``. Unconfirmed carries
are treated as missing, so the engine keeps asking until the LLM extracts
new values for them (which flips the meta to confirmed in
``IntakeEngine.next_turn``).
"""
from __future__ import annotations

from domain.intake.templates.medical_general import GeneralMedicalExtractor


def _seed_collected(*, confirmed: bool):
    """Build a `collected` dict identical to a fresh carry-forward bootstrap,
    with all 5 phase-2 fields seeded plus the meta marking each
    `confirmed_by_patient` per the parameter."""
    cf_meta = {
        f: {
            "source_record_id": 1,
            "source_date": "2026-04-25T00:00:00",
            "confirmed_by_patient": confirmed,
        }
        for f in (
            "past_history", "allergy_history", "family_history",
            "personal_history", "marital_reproductive",
        )
    }
    return {
        "chief_complaint": "腹痛",
        "present_illness": "下腹部及肚脐周围疼痛",
        "past_history": "无",
        "allergy_history": "无",
        "family_history": "父亲糖尿病",
        "personal_history": "无",
        "marital_reproductive": "未婚",
        "_carry_forward_meta": cf_meta,
    }


def test_unconfirmed_carry_forward_counts_as_missing():
    extractor = GeneralMedicalExtractor()
    state = extractor.completeness(
        _seed_collected(confirmed=False), mode="patient",
    )
    assert state.can_complete is False, (
        "unconfirmed carry-forward fields must not satisfy completeness"
    )
    assert set(state.required_missing) == {
        "past_history", "allergy_history", "family_history",
        "personal_history", "marital_reproductive",
    }


def test_confirmed_carry_forward_counts_as_filled():
    extractor = GeneralMedicalExtractor()
    state = extractor.completeness(
        _seed_collected(confirmed=True), mode="patient",
    )
    assert state.can_complete is True
    assert state.required_missing == []


def test_mixed_confirmed_partial_completeness():
    collected = _seed_collected(confirmed=False)
    collected["_carry_forward_meta"]["allergy_history"]["confirmed_by_patient"] = True
    collected["_carry_forward_meta"]["past_history"]["confirmed_by_patient"] = True

    state = GeneralMedicalExtractor().completeness(collected, mode="patient")
    assert state.can_complete is False
    assert set(state.required_missing) == {
        "family_history", "personal_history", "marital_reproductive",
    }


def test_no_carry_forward_meta_defaults_to_filled():
    """A field without any carry_forward_meta entry is treated normally —
    if value is non-empty, it counts as filled (covers the regular intake
    path where the field was extracted from patient input directly)."""
    collected = {
        "chief_complaint": "腹痛",
        "present_illness": "下腹部疼痛",
        "past_history": "无",
        "allergy_history": "无",
        "family_history": "无",
        "personal_history": "无",
        "marital_reproductive": "未婚",
        # no _carry_forward_meta
    }
    state = GeneralMedicalExtractor().completeness(collected, mode="patient")
    assert state.can_complete is True
