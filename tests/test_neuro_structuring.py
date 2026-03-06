"""Tests for services/neuro_structuring.py — LLM is mocked.

Verifies that:
- Markdown response is correctly parsed into NeuroCase + ExtractionLog
- imaging: [] when imaging section is absent from case
- Malformed JSON raises ValueError
- LLM is called with the correct system prompt content
- DB row scalar fields are promoted correctly by save_neuro_case
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.neuro_case import ExtractionLog, NeuroCase
from services.neuro_structuring import _parse_markdown_output, extract_neuro_case
from db.crud import get_neuro_cases_for_doctor, save_neuro_case


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_neuro_case_dict(**overrides) -> dict:
    base = {
        "case_id": "CVD-TEST-001",
        "patient_profile": {"name": "张三", "gender": "male", "age": 65},
        "encounter": {"type": "inpatient"},
        "chief_complaint": {"text": "突发右侧肢体无力伴言语不清2小时", "duration": "2小时"},
        "hpi": {"onset": "突发", "progression": "持续", "associated_symptoms": [], "prior_treatment": None},
        "past_history": {},
        "risk_factors": {
            "hypertension": {"has_htn": "yes", "years": 10, "control_status": "uncontrolled"},
            "diabetes": "no",
            "hyperlipidemia": "yes",
            "smoking": "yes",
            "drinking": "no",
            "family_history_cvd": "unknown",
        },
        "physical_exam": {"bp_systolic": 180, "bp_diastolic": 110},
        "neuro_exam": {"nihss_total": 8, "consciousness": "清醒", "speech": "构音障碍"},
        "imaging": [
            {
                "modality": "MRI",
                "datetime": None,
                "summary": "左侧基底节区急性梗死",
                "findings": [
                    {
                        "vessel": "大脑中动脉",
                        "lesion_type": "occlusion",
                        "severity_percent": None,
                        "side": "left",
                        "collateral": None,
                        "notes": None,
                    }
                ],
            }
        ],
        "labs": [
            {
                "name": "血糖",
                "datetime": None,
                "result": "7.2",
                "unit": "mmol/L",
                "flag": "high",
                "source_text": "血糖7.2 mmol/L",
            }
        ],
        "diagnosis": {
            "primary": "急性脑梗死（左侧基底节区）",
            "secondary": [],
            "stroke_type": "ischemic",
            "territory": "MCA",
            "etiology_toast": "LAA",
        },
        "plan": {"orders": [], "thrombolysis": "rt-PA 0.9mg/kg iv", "antiplatelet": "阿司匹林"},
        "provenance": {"source": "dictation", "recorded_at": None},
    }
    base.update(overrides)
    return base


def _make_log_dict(**overrides) -> dict:
    base = {
        "missing_fields": ["family_history_cvd"],
        "ambiguities": [],
        "normalization_notes": ["NIHSS normalized from raw score"],
        "confidence_by_module": {"imaging": 0.9, "diagnosis": 0.95},
    }
    base.update(overrides)
    return base


def _make_markdown(case_dict: dict, log_dict: dict) -> str:
    return (
        "## Structured_JSON\n\n"
        "```json\n"
        + json.dumps(case_dict, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        "## Extraction_Log\n\n"
        "```json\n"
        + json.dumps(log_dict, ensure_ascii=False, indent=2)
        + "\n```\n"
    )


def _make_completion(md_text: str):
    msg = MagicMock()
    msg.content = md_text
    choice = MagicMock()
    choice.message = msg
    completion = MagicMock()
    completion.choices = [choice]
    return completion


@pytest.fixture
def mock_llm(monkeypatch):
    monkeypatch.setenv("STRUCTURING_LLM", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key-for-tests")
    mock_client = AsyncMock()
    mock_create = AsyncMock()
    mock_client.chat.completions.create = mock_create
    with patch("services.neuro_structuring.AsyncOpenAI", return_value=mock_client):
        yield mock_create


# ---------------------------------------------------------------------------
# test_parse_markdown_extracts_json
# ---------------------------------------------------------------------------


def test_parse_markdown_extracts_json():
    case_dict = _make_neuro_case_dict()
    log_dict = _make_log_dict()
    md = _make_markdown(case_dict, log_dict)

    neuro_case, _ = _parse_markdown_output(md)

    assert isinstance(neuro_case, NeuroCase)
    assert neuro_case.patient_profile.get("name") == "张三"
    assert neuro_case.patient_profile.get("age") == 65
    assert neuro_case.chief_complaint.get("text") == "突发右侧肢体无力伴言语不清2小时"
    assert neuro_case.neuro_exam.get("nihss_total") == 8
    assert neuro_case.diagnosis.get("primary") == "急性脑梗死（左侧基底节区）"
    assert neuro_case.diagnosis.get("stroke_type") == "ischemic"


# ---------------------------------------------------------------------------
# test_parse_markdown_extracts_log
# ---------------------------------------------------------------------------


def test_parse_markdown_extracts_log():
    case_dict = _make_neuro_case_dict()
    log_dict = _make_log_dict()
    md = _make_markdown(case_dict, log_dict)

    _, extraction_log = _parse_markdown_output(md)

    assert isinstance(extraction_log, ExtractionLog)
    assert "family_history_cvd" in extraction_log.missing_fields
    assert extraction_log.normalization_notes == ["NIHSS normalized from raw score"]
    assert extraction_log.confidence_by_module.get("imaging") == pytest.approx(0.9)
    assert extraction_log.confidence_by_module.get("diagnosis") == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# test_missing_imaging_returns_empty_list
# ---------------------------------------------------------------------------


def test_missing_imaging_returns_empty_list():
    case_dict = _make_neuro_case_dict(imaging=[])
    log_dict = _make_log_dict()
    md = _make_markdown(case_dict, log_dict)

    neuro_case, _ = _parse_markdown_output(md)

    assert neuro_case.imaging == []


# ---------------------------------------------------------------------------
# test_malformed_json_raises_value_error
# ---------------------------------------------------------------------------


def test_malformed_json_raises_value_error():
    bad_md = (
        "## Structured_JSON\n\n"
        "```json\n"
        "{ this is not valid JSON !!! \n"
        "```\n\n"
        "## Extraction_Log\n\n"
        "```json\n"
        "{}\n"
        "```\n"
    )
    with pytest.raises(ValueError, match="NeuroCase JSON parse error"):
        _parse_markdown_output(bad_md)


# ---------------------------------------------------------------------------
# test_extract_neuro_case_calls_llm_with_prompt
# ---------------------------------------------------------------------------


async def test_extract_neuro_case_calls_llm_with_prompt(mock_llm):
    case_dict = _make_neuro_case_dict()
    log_dict = _make_log_dict()
    md = _make_markdown(case_dict, log_dict)
    mock_llm.return_value = _make_completion(md)

    neuro_case, _ = await extract_neuro_case("患者张三，男，65岁，突发右侧肢体无力2小时")

    assert mock_llm.called
    call_kwargs = mock_llm.call_args.kwargs
    messages = call_kwargs["messages"]
    system_msg = messages[0]
    assert system_msg["role"] == "system"
    # Seed prompt contains these key phrases
    assert "Structured_JSON" in system_msg["content"]
    assert "Extraction_Log" in system_msg["content"]
    assert "NIHSS" in system_msg["content"]
    # User message is the raw input
    assert messages[-1]["role"] == "user"
    assert "张三" in messages[-1]["content"]
    # LLM call params
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["max_tokens"] == 3000
    assert isinstance(neuro_case, NeuroCase)


# ---------------------------------------------------------------------------
# test_save_neuro_case_promotes_scalars
# ---------------------------------------------------------------------------


async def test_save_neuro_case_promotes_scalars(session_factory):
    case_dict = _make_neuro_case_dict()
    log_dict = _make_log_dict()
    neuro_case = NeuroCase.model_validate(case_dict)
    extraction_log = ExtractionLog.model_validate(log_dict)

    async with session_factory() as session:
        row = await save_neuro_case(session, "doc_001", neuro_case, extraction_log)

    assert row.id is not None
    assert row.doctor_id == "doc_001"
    assert row.patient_name == "张三"
    assert row.gender == "male"
    assert row.age == 65
    assert row.encounter_type == "inpatient"
    assert row.chief_complaint == "突发右侧肢体无力伴言语不清2小时"
    assert row.primary_diagnosis == "急性脑梗死（左侧基底节区）"
    assert row.nihss == 8

    # Full JSON blobs round-trip
    raw = json.loads(row.raw_json)
    assert raw["patient_profile"]["name"] == "张三"
    log_parsed = json.loads(row.extraction_log_json)
    assert "family_history_cvd" in log_parsed["missing_fields"]


async def test_save_neuro_case_invalid_numeric_fields_coerce_to_none(session_factory):
    case_dict = _make_neuro_case_dict(
        patient_profile={"name": "王五", "gender": "male", "age": "unknown"},
        neuro_exam={"nihss_total": "N/A"},
    )
    log_dict = _make_log_dict()
    neuro_case = NeuroCase.model_validate(case_dict)
    extraction_log = ExtractionLog.model_validate(log_dict)

    async with session_factory() as session:
        row = await save_neuro_case(session, "doc_bad_num", neuro_case, extraction_log)

    assert row.age is None
    assert row.nihss is None


async def test_get_neuro_cases_for_doctor_returns_only_target_doctor(session_factory):
    case_a = NeuroCase.model_validate(_make_neuro_case_dict())
    case_b = NeuroCase.model_validate(
        _make_neuro_case_dict(
            case_id="CVD-TEST-002",
            patient_profile={"name": "李四", "gender": "female", "age": 70},
            chief_complaint={"text": "头晕", "duration": "1天"},
        )
    )
    log = ExtractionLog.model_validate(_make_log_dict())

    async with session_factory() as session:
        await save_neuro_case(session, "doc_A", case_a, log)
        await save_neuro_case(session, "doc_A", case_b, log)
        await save_neuro_case(session, "doc_B", case_b, log)
        rows = await get_neuro_cases_for_doctor(session, "doc_A", limit=10)

    assert len(rows) == 2
    assert all(r.doctor_id == "doc_A" for r in rows)
