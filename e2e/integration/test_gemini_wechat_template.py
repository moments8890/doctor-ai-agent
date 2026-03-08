"""Gemini template integration tests for WeChat-like scenarios.

Run:
  export RUN_GEMINI_TEMPLATE=1
  # provider is configurable (e.g. ollama/gemini/deepseek)
  # optional for follow-up task assertions:
  export AUTO_FOLLOWUP_TASKS_ENABLED=true
  pytest e2e/integration/test_gemini_wechat_template.py -v
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from e2e.integration.conftest import DB_PATH, chat


if os.environ.get("RUN_GEMINI_TEMPLATE") != "1":
    pytest.skip(
        "Set RUN_GEMINI_TEMPLATE=1 to run Gemini template integration cases.",
        allow_module_level=True,
    )


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "tests" / "fixtures" / "e2e" / "gemini_wechat_scenarios_v1.json"


def _load_cases() -> List[Dict]:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, list) and raw, "gemini_wechat_scenarios_v1.json should be a non-empty array"
    return raw


def _patient_row(doctor_id: str, patient_name: str) -> Optional[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, name, primary_risk_level
            FROM patients
            WHERE doctor_id=? AND name=?
            ORDER BY id DESC LIMIT 1
            """,
            (doctor_id, patient_name),
        ).fetchone()
        return row
    finally:
        conn.close()


def _follow_up_task(doctor_id: str, patient_id: int) -> Optional[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, due_at, task_type, status
            FROM doctor_tasks
            WHERE doctor_id=? AND patient_id=? AND task_type='follow_up'
            ORDER BY id DESC LIMIT 1
            """,
            (doctor_id, patient_id),
        ).fetchone()
        return row
    finally:
        conn.close()


def _contains_all(text: Optional[str], keywords: List[str]) -> bool:
    if not keywords:
        return True
    if not text:
        return False
    return all(k in text for k in keywords)


def _contains_any(text: Optional[str], keywords: List[str]) -> bool:
    if not keywords:
        return True
    if not text:
        return False
    return any(k in text for k in keywords)


def _join_fields(record: Dict, fields: List[str]) -> str:
    parts: List[str] = []
    for field in fields:
        value = record.get(field)
        if value:
            parts.append(str(value))
    return " | ".join(parts)


def _is_ollama_provider() -> bool:
    return (
        os.environ.get("ROUTING_LLM") == "ollama"
        or os.environ.get("STRUCTURING_LLM") == "ollama"
    )


@pytest.mark.integration
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["case_id"])
def test_gemini_wechat_scenario_template(case: Dict):
    doctor_id = "inttest_gemini_%s_%s" % (case["case_id"].lower(), uuid.uuid4().hex[:6])
    expected = case["expected"]

    data = chat(case["input_text"], doctor_id=doctor_id)
    record = data.get("record")
    assert record is not None, "record should not be null"
    chief_text = _join_fields(record, ["chief_complaint", "history_of_present_illness", "diagnosis"])
    diagnosis_text = _join_fields(record, ["diagnosis", "history_of_present_illness", "auxiliary_examinations", "treatment_plan"])
    treatment_text = _join_fields(record, ["treatment_plan", "follow_up_plan", "diagnosis", "auxiliary_examinations"])
    aux_text = _join_fields(record, ["auxiliary_examinations", "history_of_present_illness", "treatment_plan"])
    follow_text = _join_fields(record, ["follow_up_plan", "treatment_plan"])

    assert _contains_all(chief_text, expected.get("chief_complaint_contains", []))
    assert _contains_any(diagnosis_text, expected.get("diagnosis_contains_any", []))
    assert _contains_any(treatment_text, expected.get("treatment_plan_contains_any", []))
    assert _contains_any(aux_text, expected.get("auxiliary_examinations_contains_any", []))
    assert _contains_any(follow_text, expected.get("follow_up_plan_contains_any", []))

    patient = _patient_row(doctor_id, expected["patient_name"])
    assert patient is not None, "patient should exist in DB"
    if _is_ollama_provider():
        assert patient["primary_risk_level"] in {"low", "medium", "high", "critical"}
    else:
        assert patient["primary_risk_level"] in expected.get("risk_level_in", [])

    if expected.get("expect_follow_up_task"):
        if os.environ.get("AUTO_FOLLOWUP_TASKS_ENABLED", "").lower() not in {"1", "true", "yes", "on"}:
            pytest.skip("AUTO_FOLLOWUP_TASKS_ENABLED is off; skip follow_up task assertion.")
        task = _follow_up_task(doctor_id, int(patient["id"]))
        assert task is not None, "expected follow_up task not found"
        assert task["task_type"] == "follow_up"
        assert task["status"] == "pending"
        target = int(expected.get("follow_up_task_due_days", 7))
        days = (datetime.fromisoformat(task["due_at"]) - datetime.now(timezone.utc)).days
        assert abs(days - target) <= 2
