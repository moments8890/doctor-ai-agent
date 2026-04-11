"""Tests for the DoctorPersona model."""
import json
import pytest
from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS

def test_empty_persona_fields_structure():
    fields = EMPTY_PERSONA_FIELDS()
    assert set(fields.keys()) == {"reply_style", "closing", "structure", "avoid", "edits"}
    for v in fields.values():
        assert v == []

def test_persona_model_defaults():
    """Column defaults are applied at DB-insert time; verify them via column metadata."""
    cols = DoctorPersona.__table__.columns
    assert cols["status"].default.arg == "draft"
    assert cols["onboarded"].default.arg is False
    assert cols["edit_count"].default.arg == 0
    assert cols["version"].default.arg == 1

def test_fields_property_roundtrip():
    p = DoctorPersona(doctor_id="doc_1")
    p.fields_json = json.dumps(EMPTY_PERSONA_FIELDS())
    fields = p.fields
    fields["reply_style"].append({"id": "ps_1", "text": "test", "source": "manual", "usage_count": 0})
    p.fields = fields
    assert len(p.fields["reply_style"]) == 1
    assert p.fields["reply_style"][0]["text"] == "test"

def test_all_rules():
    p = DoctorPersona(doctor_id="doc_1")
    fields = EMPTY_PERSONA_FIELDS()
    fields["reply_style"].append({"id": "ps_1", "text": "a", "source": "manual", "usage_count": 0})
    fields["avoid"].append({"id": "ps_2", "text": "b", "source": "manual", "usage_count": 0})
    p.fields = fields
    assert len(p.all_rules()) == 2

def test_render_for_prompt_empty():
    p = DoctorPersona(doctor_id="doc_1")
    p.fields_json = json.dumps(EMPTY_PERSONA_FIELDS())
    assert p.render_for_prompt() == ""

def test_render_for_prompt_with_rules():
    p = DoctorPersona(doctor_id="doc_1")
    fields = EMPTY_PERSONA_FIELDS()
    fields["reply_style"].append({"id": "ps_1", "text": "口语化", "source": "manual", "usage_count": 5})
    fields["avoid"].append({"id": "ps_2", "text": "不提风险", "source": "manual", "usage_count": 10})
    p.fields = fields
    result = p.render_for_prompt()
    assert "回避内容" in result
    assert "[P-ps_2]" in result
    assert "回复风格" in result
    assert "[P-ps_1]" in result
    # avoid should come before reply_style (priority order)
    assert result.index("回避内容") < result.index("回复风格")

def test_render_for_prompt_respects_max_rules():
    p = DoctorPersona(doctor_id="doc_1")
    fields = EMPTY_PERSONA_FIELDS()
    for i in range(20):
        fields["reply_style"].append({"id": f"ps_{i}", "text": f"rule {i}", "source": "manual", "usage_count": 0})
    p.fields = fields
    result = p.render_for_prompt(max_rules=3)
    assert result.count("[P-") == 3
