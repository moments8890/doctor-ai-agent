"""FormSatisfactionTemplate — bindings + registry entry."""
from __future__ import annotations

import pytest

from domain.interview.templates import TEMPLATES, get_template
from domain.interview.templates.form_satisfaction import (
    FormSatisfactionExtractor, FormSatisfactionTemplate,
)
from domain.interview.writers import FormResponseWriter


def test_form_satisfaction_v1_registered():
    t = get_template("form_satisfaction_v1")
    assert isinstance(t, FormSatisfactionTemplate)


def test_kind_is_form_not_medical():
    t = get_template("form_satisfaction_v1")
    assert t.kind == "form"


def test_does_not_require_doctor_review():
    t = get_template("form_satisfaction_v1")
    assert t.requires_doctor_review is False


def test_supported_modes_is_patient_only():
    t = get_template("form_satisfaction_v1")
    assert t.supported_modes == ("patient",)


def test_wires_form_response_writer():
    t = get_template("form_satisfaction_v1")
    assert isinstance(t.writer, FormResponseWriter)


def test_no_batch_extractor():
    t = get_template("form_satisfaction_v1")
    assert t.batch_extractor is None


def test_post_confirm_hooks_are_empty():
    t = get_template("form_satisfaction_v1")
    assert t.post_confirm_hooks["patient"] == []


def test_registry_contains_both_templates():
    assert "medical_general_v1" in TEMPLATES
    assert "form_satisfaction_v1" in TEMPLATES
    # Phase 4 r2 Task 8: registry now also contains medical_neuro_v1.
    assert len(TEMPLATES) == 3
