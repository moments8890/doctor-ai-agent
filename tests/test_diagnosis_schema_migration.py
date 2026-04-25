"""Integration tests for the 2026-04-25 diagnosis schema migration.

Locks in the new-schema behavior end-to-end without an LLM:
- Sufficiency rule pre-check (locked plan rule 4-6)
- Pydantic dual-schema acceptance (old + new)
- Validation passes new fields through
- API mapper exposes new fields and parses KB-N from trigger_rule_ids

LLM-level behavior (does the prompt actually produce the new shape?) is
covered by `tests/prompts/cases/diagnosis.yaml` via promptfoo when an
API key is set.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("ENVIRONMENT", "development")
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from domain.diagnosis_models import (
    DiagnosisDifferential, DiagnosisWorkup, DiagnosisTreatment, DiagnosisLLMResponse,
)
from domain.diagnosis_pipeline import (
    _is_sufficient_for_diagnosis, _validate_and_coerce_result, _clean_str_list,
)


# ── Sufficiency rule (locked plan rule 4) ───────────────────────────────


def test_sufficiency_empty_chief_complaint_returns_false():
    assert _is_sufficient_for_diagnosis({"chief_complaint": ""}) is False
    assert _is_sufficient_for_diagnosis({}) is False


def test_sufficiency_chief_complaint_only_returns_false():
    assert _is_sufficient_for_diagnosis({"chief_complaint": "头痛"}) is False


def test_sufficiency_chief_plus_present_illness_returns_true():
    assert _is_sufficient_for_diagnosis({
        "chief_complaint": "头痛",
        "present_illness": "持续2周",
    }) is True


def test_sufficiency_chief_plus_physical_exam_returns_true():
    assert _is_sufficient_for_diagnosis({
        "chief_complaint": "胸痛",
        "physical_exam": "BP 120/80",
    }) is True


def test_sufficiency_chief_plus_auxiliary_exam_returns_true():
    assert _is_sufficient_for_diagnosis({
        "chief_complaint": "头痛",
        "auxiliary_exam": "MRI示占位",
    }) is True


# ── Pydantic dual-schema acceptance ─────────────────────────────────────


def test_pydantic_accepts_new_schema():
    """LLM may emit the new schema with evidence/risk_signals/trigger_rule_ids."""
    d = DiagnosisDifferential(
        condition="急性冠脉综合征",
        evidence=["突发胸痛", "伴出汗", "高血压8年"],
        risk_signals=["持续胸痛>30分钟", "ST段改变"],
        trigger_rule_ids=["KB-1"],
    )
    assert d.evidence == ["突发胸痛", "伴出汗", "高血压8年"]
    assert d.risk_signals == ["持续胸痛>30分钟", "ST段改变"]
    assert d.trigger_rule_ids == ["KB-1"]
    assert d.confidence == ""  # legacy field unset
    assert d.detail == ""


def test_pydantic_accepts_old_schema():
    """Backward compat: old prompt outputs still parse correctly."""
    d = DiagnosisDifferential(condition="偏头痛", confidence="中", detail="慢性头痛")
    assert d.condition == "偏头痛"
    assert d.confidence == "中"
    assert d.detail == "慢性头痛"
    # New fields default to empty
    assert d.evidence == []
    assert d.risk_signals == []
    assert d.trigger_rule_ids == []


def test_pydantic_workup_treatment_have_new_fields():
    w = DiagnosisWorkup(
        test="心电图",
        evidence=["突发胸痛"],
        risk_signals=["ST改变"],
        trigger_rule_ids=["KB-1"],
        urgency="紧急",
    )
    assert w.evidence == ["突发胸痛"]

    t = DiagnosisTreatment(
        intervention="药物",
        drug_class="抗血小板药物",
        evidence=["确诊ACS"],
        trigger_rule_ids=["KB-2"],
    )
    assert t.evidence == ["确诊ACS"]


# ── Validation / coercion passes new fields through ─────────────────────


def test_validate_passes_new_fields_through():
    resp = DiagnosisLLMResponse(
        differentials=[DiagnosisDifferential(
            condition="急性冠脉综合征",
            evidence=["突发胸痛", "伴出汗"],
            risk_signals=["持续>30分钟"],
            trigger_rule_ids=["KB-1"],
        )],
        workup=[DiagnosisWorkup(
            test="心电图",
            evidence=["突发胸痛+高血压"],
            urgency="紧急",
            trigger_rule_ids=["KB-1"],
        )],
        treatment=[],
    )
    out = _validate_and_coerce_result(resp)
    assert out is not None
    assert len(out["differentials"]) == 1
    d = out["differentials"][0]
    assert d["evidence"] == ["突发胸痛", "伴出汗"]
    assert d["risk_signals"] == ["持续>30分钟"]
    assert d["trigger_rule_ids"] == ["KB-1"]
    assert d["confidence"] == ""  # legacy fallback empty
    assert len(out["workup"]) == 1
    assert out["workup"][0]["evidence"] == ["突发胸痛+高血压"]
    assert out["workup"][0]["trigger_rule_ids"] == ["KB-1"]


def test_validate_drops_empty_strings_from_arrays():
    """_clean_str_list drops empty/whitespace strings (pydantic enforces str type at parse time)."""
    resp = DiagnosisLLMResponse(
        differentials=[DiagnosisDifferential(
            condition="X",
            evidence=["fact1", "", "  ", "fact2"],
            risk_signals=["", "signal", "  "],
            trigger_rule_ids=["KB-1", ""],
        )],
    )
    out = _validate_and_coerce_result(resp)
    d = out["differentials"][0]
    assert d["evidence"] == ["fact1", "fact2"]  # empties stripped
    assert d["risk_signals"] == ["signal"]
    assert d["trigger_rule_ids"] == ["KB-1"]


def test_validate_returns_none_on_empty_differentials():
    """Sufficiency rule semantics: empty input → None (caller returns insufficient_data)."""
    resp = DiagnosisLLMResponse(differentials=[], workup=[], treatment=[])
    out = _validate_and_coerce_result(resp)
    assert out is None


# ── _clean_str_list helper ──────────────────────────────────────────────


def test_clean_str_list_normal():
    assert _clean_str_list(["a", "b"]) == ["a", "b"]
    assert _clean_str_list(["  a  ", "b"]) == ["a", "b"]


def test_clean_str_list_drops_empties():
    assert _clean_str_list(["", "a", None, "  ", "b"]) == ["a", "b"]


def test_clean_str_list_non_list_returns_empty():
    assert _clean_str_list(None) == []
    assert _clean_str_list("not a list") == []
    assert _clean_str_list({}) == []


# ── API mapper ──────────────────────────────────────────────────────────


def test_api_mapper_exposes_new_fields_and_parses_kb_ids():
    """API mapper should decode JSON columns and parse KB-N from trigger_rule_ids."""
    from channels.web.doctor_dashboard.diagnosis_handlers import _suggestion_to_dict

    class MockRow:
        id = 1
        record_id = 100
        section = "differential"
        content = "右额叶脑膜瘤"
        detail = ""
        confidence = ""
        urgency = None
        intervention = None
        evidence_json = json.dumps(["MRI均匀强化", "宽基底"], ensure_ascii=False)
        risk_signals_json = json.dumps(["头痛加剧"], ensure_ascii=False)
        trigger_rule_ids_json = json.dumps(["KB-12"], ensure_ascii=False)
        decision = None
        edited_text = None
        reason = None
        is_custom = False
        created_at = datetime.now()
        decided_at = None

    out = _suggestion_to_dict(MockRow())
    assert out["evidence"] == ["MRI均匀强化", "宽基底"]
    assert out["risk_signals"] == ["头痛加剧"]
    assert out["trigger_rule_ids"] == ["KB-12"]
    # KB-N parsed for citation chips
    assert out["cited_knowledge_ids"] == [12]


def test_api_mapper_legacy_row_still_works():
    """Old rows with detail/confidence and no JSON columns still serialize."""
    from channels.web.doctor_dashboard.diagnosis_handlers import _suggestion_to_dict

    class MockRow:
        id = 2
        record_id = 100
        section = "differential"
        content = "偏头痛"
        detail = "慢性头痛 [KB-5] 持续3月"
        confidence = "中"
        urgency = None
        intervention = None
        evidence_json = None
        risk_signals_json = None
        trigger_rule_ids_json = None
        decision = None
        edited_text = None
        reason = None
        is_custom = False
        created_at = datetime.now()
        decided_at = None

    out = _suggestion_to_dict(MockRow())
    assert out["confidence"] == "中"
    assert "[KB-5]" not in out["detail"]  # citation markers stripped
    assert out["cited_knowledge_ids"] == [5]  # parsed from legacy detail
    assert out["evidence"] == []  # new fields empty for legacy rows
    assert out["risk_signals"] == []
    assert out["trigger_rule_ids"] == []
