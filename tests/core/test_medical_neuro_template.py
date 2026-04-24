"""medical_neuro_v1 — template binding + hook composition (Phase 4 r2 Task 8)."""
from __future__ import annotations

from domain.interview.hooks.medical import (
    GenerateFollowupTasksHook, NotifyDoctorHook, TriggerDiagnosisPipelineHook,
)
from domain.interview.hooks.safety import SafetyScreenHook
from domain.interview.templates import get_template
from domain.interview.templates.medical_general import (
    MedicalBatchExtractor, MedicalRecordWriter,
)
from domain.interview.templates.medical_neuro import (
    GeneralNeuroExtractor, GeneralNeuroTemplate,
)


def test_medical_neuro_v1_registered():
    t = get_template("medical_neuro_v1")
    assert isinstance(t, GeneralNeuroTemplate)


def test_supports_both_modes():
    t = get_template("medical_neuro_v1")
    assert t.supported_modes == ("patient", "doctor")


def test_uses_neuro_extractor():
    t = get_template("medical_neuro_v1")
    assert isinstance(t.extractor, GeneralNeuroExtractor)


def test_uses_medical_record_writer():
    """No neuro-specific writer — reuse the general MedicalRecordWriter."""
    t = get_template("medical_neuro_v1")
    assert isinstance(t.writer, MedicalRecordWriter)


def test_uses_medical_batch_extractor():
    t = get_template("medical_neuro_v1")
    assert isinstance(t.batch_extractor, MedicalBatchExtractor)


def test_patient_hooks_include_diagnosis_notify_and_safety():
    t = get_template("medical_neuro_v1")
    patient_hooks = t.post_confirm_hooks["patient"]
    hook_types = {type(h) for h in patient_hooks}
    assert TriggerDiagnosisPipelineHook in hook_types
    assert NotifyDoctorHook in hook_types
    assert SafetyScreenHook in hook_types


def test_doctor_hooks_include_followup_and_safety_but_not_diagnosis():
    """§8 resolution: doctor-mode runs follow-up generation + safety screen,
    but deliberately does NOT fire the diagnosis pipeline (doctor is the
    decider, not the subject of LLM triage)."""
    t = get_template("medical_neuro_v1")
    doctor_hooks = t.post_confirm_hooks["doctor"]
    hook_types = {type(h) for h in doctor_hooks}
    assert GenerateFollowupTasksHook in hook_types
    assert SafetyScreenHook in hook_types
    assert TriggerDiagnosisPipelineHook not in hook_types


def test_safety_screen_runs_both_modes():
    t = get_template("medical_neuro_v1")
    patient_types = {type(h) for h in t.post_confirm_hooks["patient"]}
    doctor_types = {type(h) for h in t.post_confirm_hooks["doctor"]}
    assert SafetyScreenHook in patient_types
    assert SafetyScreenHook in doctor_types


def test_requires_doctor_review_true():
    t = get_template("medical_neuro_v1")
    assert t.requires_doctor_review is True


def test_config_max_turns_30():
    t = get_template("medical_neuro_v1")
    assert t.config.max_turns == 30
