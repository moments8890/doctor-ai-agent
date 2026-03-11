"""Entity extraction layer tests: verify provenance tracking and content signals."""

import pytest
from services.ai.intent import Intent, IntentResult
from services.intent_workflow.entities import extract_entities


def _raw(intent=Intent.add_record, name=None, gender=None, age=None, extra=None):
    return IntentResult(
        intent=intent,
        patient_name=name,
        gender=gender,
        age=age,
        extra_data=extra or {},
    )


# ── Clinical content signal detection ─────────────────────────────────────────


def test_clinical_content_signal_detected():
    """Text with clinical keywords should flag has_clinical_content."""
    entities = extract_entities(
        _raw(Intent.create_patient, name="张三"),
        decision_source="llm",
        text="张三，男，38岁，突发胸痛两小时伴大汗",
        history=[],
        doctor_id="test_doc",
    )
    assert entities.extra_data.get("has_clinical_content") is True


def test_no_clinical_content_signal_for_plain_create():
    """Text without clinical keywords should not flag has_clinical_content."""
    entities = extract_entities(
        _raw(Intent.create_patient, name="张三"),
        decision_source="llm",
        text="新患者张三，男，38岁",
        history=[],
        doctor_id="test_doc",
    )
    assert entities.extra_data.get("has_clinical_content") is not True


def test_reminder_signal_detected():
    """Text with reminder patterns should flag has_reminder."""
    entities = extract_entities(
        _raw(Intent.create_patient, name="张三"),
        decision_source="llm",
        text="新患者张三，提醒我明天复查血压",
        history=[],
        doctor_id="test_doc",
    )
    assert entities.extra_data.get("has_reminder") is True


# ── Provenance tracking ──────────────────────────────────────────────────────


def test_followup_name_has_followup_source():
    entities = extract_entities(
        _raw(Intent.add_record),
        decision_source="llm",
        text="张三",
        history=[],
        doctor_id="test_doc",
        followup_name="张三",
    )
    assert entities.patient_name is not None
    assert entities.patient_name.source == "followup"
    assert entities.patient_name.value == "张三"


def test_llm_name_has_llm_source():
    entities = extract_entities(
        _raw(Intent.add_record, name="李四"),
        decision_source="llm",
        text="李四胸痛两小时",
        history=[],
        doctor_id="test_doc",
    )
    assert entities.patient_name is not None
    assert entities.patient_name.source == "llm"
    assert entities.patient_name.value == "李四"


def test_fast_route_source_propagated():
    entities = extract_entities(
        _raw(Intent.add_record, name="王五", extra={"patient_source": "session"}),
        decision_source="fast_route",
        text="王五胸痛两小时",
        history=[],
        doctor_id="test_doc",
    )
    assert entities.patient_name is not None
    assert entities.patient_name.source == "session"


def test_gender_and_age_propagated():
    entities = extract_entities(
        _raw(Intent.create_patient, name="张三", gender="男", age=38),
        decision_source="llm",
        text="新患者张三，男，38岁",
        history=[],
        doctor_id="test_doc",
    )
    assert entities.gender is not None
    assert entities.gender.value == "男"
    assert entities.age is not None
    assert entities.age.value == 38


def test_non_patient_intent_skips_name_fallback():
    """For intents like list_tasks, patient_name should not be resolved via fallbacks."""
    entities = extract_entities(
        _raw(Intent.list_tasks),
        decision_source="llm",
        text="查看待办",
        history=[],
        doctor_id="test_doc",
    )
    assert entities.patient_name is None
