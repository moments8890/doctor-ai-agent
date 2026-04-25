"""Tests for the KB → patient-facing dual-opt-in gate.

A KB item is patient-facing only when BOTH the item is flagged
patient_safe AND the owning doctor has completed kb_curation_onboarding.
Per-item opt-in alone isn't enough (Codex round 2 pushback) — requires
the deliberate doctor-level walkthrough first.
"""
from domain.knowledge.curation_gate import is_patient_safe


class FakeItem:
    def __init__(self, patient_safe: bool):
        self.patient_safe = patient_safe


class FakeDoctor:
    def __init__(self, done: bool):
        self.kb_curation_onboarding_done = done


def test_item_safe_and_doctor_done_returns_true():
    assert is_patient_safe(FakeItem(True), FakeDoctor(True)) is True


def test_item_safe_but_doctor_not_done_returns_false():
    # Item flagged patient_safe but doctor hasn't walked through onboarding —
    # gate refuses. This is the Codex round 2 fix.
    assert is_patient_safe(FakeItem(True), FakeDoctor(False)) is False


def test_item_unsafe_doctor_done_returns_false():
    assert is_patient_safe(FakeItem(False), FakeDoctor(True)) is False


def test_item_unsafe_doctor_not_done_returns_false():
    assert is_patient_safe(FakeItem(False), FakeDoctor(False)) is False


def test_none_inputs_return_false():
    # Defensive: missing item or missing doctor should never return True.
    assert is_patient_safe(None, FakeDoctor(True)) is False
    assert is_patient_safe(FakeItem(True), None) is False
    assert is_patient_safe(None, None) is False
