"""Tests for persona CRUD operations."""
import json
import pytest
from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS
from db.crud.persona import (
    generate_rule_id,
    add_rule_to_persona,
    remove_rule_from_persona,
    update_rule_in_persona,
)

@pytest.fixture
def sample_rule():
    return {"id": "ps_1", "text": "口语化回复", "source": "manual", "usage_count": 0}

@pytest.fixture
def persona():
    p = DoctorPersona(doctor_id="test_doc")
    p.fields_json = json.dumps(EMPTY_PERSONA_FIELDS())
    p.version = 1
    return p

def test_generate_rule_id_unique():
    ids = {generate_rule_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(rid.startswith("ps_") for rid in ids)

def test_add_rule_to_field(persona, sample_rule):
    add_rule_to_persona(persona, "reply_style", sample_rule)
    assert len(persona.fields["reply_style"]) == 1
    assert persona.fields["reply_style"][0]["text"] == "口语化回复"

def test_add_rule_increments_version(persona, sample_rule):
    initial_version = persona.version
    add_rule_to_persona(persona, "reply_style", sample_rule)
    assert persona.version == initial_version + 1

def test_add_rule_invalid_field(persona, sample_rule):
    with pytest.raises(ValueError, match="Unknown persona field"):
        add_rule_to_persona(persona, "nonexistent", sample_rule)

def test_remove_rule(persona, sample_rule):
    add_rule_to_persona(persona, "reply_style", sample_rule)
    remove_rule_from_persona(persona, "reply_style", "ps_1")
    assert len(persona.fields["reply_style"]) == 0

def test_remove_nonexistent_rule_is_safe(persona):
    remove_rule_from_persona(persona, "reply_style", "ps_999")
    assert len(persona.fields["reply_style"]) == 0

def test_update_rule(persona, sample_rule):
    add_rule_to_persona(persona, "reply_style", sample_rule)
    update_rule_in_persona(persona, "reply_style", "ps_1", "正式回复")
    assert persona.fields["reply_style"][0]["text"] == "正式回复"
