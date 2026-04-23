"""TEMPLATES registry + medical_general_v1 binding."""
from __future__ import annotations

import pytest

from domain.interview.templates import (
    TEMPLATES, UnknownTemplate, get_template,
)
from domain.interview.templates.medical_general import (
    GeneralMedicalExtractor, GeneralMedicalTemplate, MedicalBatchExtractor,
    MedicalRecordWriter,
)
from domain.interview.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)


def test_medical_general_v1_registered():
    t = get_template("medical_general_v1")
    assert isinstance(t, GeneralMedicalTemplate)


def test_unknown_template_raises():
    with pytest.raises(UnknownTemplate):
        get_template("nonexistent_v1")


def test_template_exposes_correct_id_and_kind():
    t = get_template("medical_general_v1")
    assert t.id == "medical_general_v1"
    assert t.kind == "medical"
    assert t.requires_doctor_review is True
    assert set(t.supported_modes) == {"patient", "doctor"}


def test_template_wires_all_components():
    t = get_template("medical_general_v1")
    assert isinstance(t.extractor, GeneralMedicalExtractor)
    assert isinstance(t.batch_extractor, MedicalBatchExtractor)
    assert isinstance(t.writer, MedicalRecordWriter)


def test_patient_hooks_include_diagnosis_and_notify():
    t = get_template("medical_general_v1")
    patient_hooks = t.post_confirm_hooks["patient"]
    hook_types = {type(h) for h in patient_hooks}
    assert TriggerDiagnosisPipelineHook in hook_types
    assert NotifyDoctorHook in hook_types


def test_doctor_hooks_include_only_followup_tasks():
    """Phase 1 preserves the asymmetric behavior: doctor-mode does NOT fire
    diagnosis. Spec §8 flags this as open product decision; Phase 4 revisits."""
    t = get_template("medical_general_v1")
    doctor_hooks = t.post_confirm_hooks["doctor"]
    hook_types = {type(h) for h in doctor_hooks}
    assert GenerateFollowupTasksHook in hook_types
    # Explicit negative assertions — this is the asymmetry spec §8 flags
    assert TriggerDiagnosisPipelineHook not in hook_types
    assert NotifyDoctorHook not in hook_types


def test_registry_is_dict_of_exactly_one_template_phase1():
    """Phase 1 ships with exactly one template. Phase 3 adds form_satisfaction_v1."""
    assert set(TEMPLATES.keys()) == {"medical_general_v1"}
