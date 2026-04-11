"""Tests for prompt composition with structured persona."""
import pytest
from agent.prompt_config import LayerConfig, FOLLOWUP_REPLY_LAYERS, DOCTOR_INTERVIEW_LAYERS, REVIEW_LAYERS, PATIENT_INTERVIEW_LAYERS


def test_followup_reply_has_load_persona_true():
    assert FOLLOWUP_REPLY_LAYERS.load_persona is True


def test_review_has_load_persona_true():
    assert REVIEW_LAYERS.load_persona is True


def test_doctor_interview_has_load_persona_false():
    assert DOCTOR_INTERVIEW_LAYERS.load_persona is False


def test_patient_interview_has_load_persona_false():
    assert PATIENT_INTERVIEW_LAYERS.load_persona is False


def test_layer_config_load_persona_default_false():
    lc = LayerConfig()
    assert lc.load_persona is False
