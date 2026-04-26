"""Tests for prompt composition with structured persona."""
import pytest
from agent.prompt_config import LayerConfig, FOLLOWUP_REPLY_LAYERS, DOCTOR_INTAKE_LAYERS, REVIEW_LAYERS, PATIENT_INTAKE_LAYERS


def test_followup_reply_has_load_persona_true():
    assert FOLLOWUP_REPLY_LAYERS.load_persona is True


def test_review_has_load_persona_true():
    assert REVIEW_LAYERS.load_persona is True


def test_doctor_intake_has_load_persona_false():
    assert DOCTOR_INTAKE_LAYERS.load_persona is False


def test_patient_intake_has_load_persona_true():
    # 2026-04-25: flipped from False — pre-visit chat must sound like the doctor
    assert PATIENT_INTAKE_LAYERS.load_persona is True


def test_layer_config_load_persona_default_false():
    lc = LayerConfig()
    assert lc.load_persona is False
