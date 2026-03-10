"""DeepSeek 对话模板数据驱动集成测试。

如何运行：
  1) export RUN_DEEPSEEK_TEMPLATE=1
  2) 可选：export AUTO_FOLLOWUP_TASKS_ENABLED=true
  3) 配置 provider 环境变量
  4) pytest e2e/integration/test_deepseek_conversations_template.py -v

DeepSeek conversation template tests (data-driven).

How to run:
  1) export RUN_DEEPSEEK_TEMPLATE=1
  2) optional: export AUTO_FOLLOWUP_TASKS_ENABLED=true
  3) configure your provider via env (e.g. ollama/deepseek/gemini)
  4) pytest e2e/integration/test_deepseek_conversations_template.py -v

Notes:
  - This is a template-style integration test for realistic conversations.
  - Assertions are keyword-based to tolerate model phrasing variance.
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


if os.environ.get("RUN_DEEPSEEK_TEMPLATE") != "1":
    pytest.skip(
        "Set RUN_DEEPSEEK_TEMPLATE=1 to run DeepSeek template integration cases.",
        allow_module_level=True,
    )


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "tests" / "fixtures" / "e2e" / "deepseek_conversations_v1.json"


def _load_cases() -> List[Dict]:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, list) and raw, "deepseek_conversations_v1.json should be a non-empty array"
    return raw


def _latest_patient_row(doctor_id: str, patient_name: str) -> Optional[sqlite3.Row]:
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


def _latest_follow_up_task(doctor_id: str, patient_id: int) -> Optional[sqlite3.Row]:
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


def _assert_record_fields(record: Dict, expected: Dict) -> None:
    """验证结构化病历各字段包含期望关键词。"""
    chief_text = _join_fields(record, ["chief_complaint", "history_of_present_illness", "diagnosis"])
    diagnosis_text = _join_fields(record, ["diagnosis", "history_of_present_illness", "auxiliary_examinations", "treatment_plan"])
    treatment_text = _join_fields(record, ["treatment_plan", "follow_up_plan", "diagnosis", "auxiliary_examinations"])
    aux_text = _join_fields(record, ["auxiliary_examinations", "history_of_present_illness", "treatment_plan"])
    follow_text = _join_fields(record, ["follow_up_plan", "treatment_plan"])

    chief_expected = expected.get("chief_complaint_contains", [])
    chief_ok = _contains_all(chief_text, chief_expected)
    if not chief_ok and _is_ollama_provider() and "门诊" in chief_expected:
        chief_ok = any(token in (chief_text or "") for token in ["复查", "复诊", "门诊"])
    assert chief_ok, "chief_complaint mismatch: %r" % (chief_text,)
    assert _contains_any(diagnosis_text, expected.get("diagnosis_contains_any", [])), (
        "diagnosis mismatch: %r" % (diagnosis_text,)
    )
    assert _contains_any(treatment_text, expected.get("treatment_plan_contains_any", [])), (
        "treatment_plan mismatch: %r" % (treatment_text,)
    )
    assert _contains_any(aux_text, expected.get("auxiliary_examinations_contains_any", [])), (
        "auxiliary_examinations mismatch: %r" % (aux_text,)
    )
    assert _contains_any(follow_text, expected.get("follow_up_plan_contains_any", [])), (
        "follow_up_plan mismatch: %r" % (follow_text,)
    )


def _assert_followup_task(doctor_id: str, patient_id: int, expected: Dict) -> None:
    """若期望随访任务，验证任务存在且 due_at 在允许偏差范围内。"""
    if not expected.get("expect_follow_up_task"):
        return
    if os.environ.get("AUTO_FOLLOWUP_TASKS_ENABLED", "").lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("AUTO_FOLLOWUP_TASKS_ENABLED is off; skip follow_up task assertion.")
    task = _latest_follow_up_task(doctor_id, patient_id)
    assert task is not None, "expected follow_up task not found"
    assert task["task_type"] == "follow_up"
    assert task["status"] == "pending"
    due_at = datetime.fromisoformat(task["due_at"])
    days = (due_at - datetime.now(timezone.utc)).days
    target = int(expected.get("follow_up_task_due_days", 7))
    assert abs(days - target) <= 2, "due_at days mismatch: got=%s expected~%s" % (days, target)


@pytest.mark.integration
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["case_id"])
def test_deepseek_conversation_case_template(case: Dict):
    """Run one realistic conversation case and verify core outputs.

    Verifies:
    - API returns structured record
    - Patient row exists and has expected risk bucket
    - Optional follow-up task is created when enabled and expected
    """
    doctor_id = "inttest_deepseek_%s_%s" % (case["case_id"].lower(), uuid.uuid4().hex[:6])
    expected = case["expected"]

    data = chat(case["input_text"], doctor_id=doctor_id)
    record = data.get("record")
    assert record is not None, "record should not be null"

    _assert_record_fields(record, expected)

    patient = _latest_patient_row(doctor_id, expected["patient_name"])
    assert patient is not None, "patient should exist in DB"
    assert patient["primary_risk_level"] in expected.get("risk_level_in", []), (
        "unexpected risk level: %r" % (patient["primary_risk_level"],)
    )

    _assert_followup_task(doctor_id, int(patient["id"]), expected)
