"""DeepSeek 对话模板数据驱动集成测试。

如何运行：
  1) export RUN_DEEPSEEK_TEMPLATE=1
  2) 配置 provider 环境变量
  3) pytest tests/integration/test_deepseek_conversations_template.py -v

DeepSeek conversation template tests (data-driven).

How to run:
  1) export RUN_DEEPSEEK_TEMPLATE=1
  2) configure your provider via env (e.g. ollama/deepseek/gemini)
  3) pytest tests/integration/test_deepseek_conversations_template.py -v

Notes:
  - This is a template-style integration test for realistic conversations.
  - Assertions are keyword-based to tolerate model phrasing variance.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from tests.integration.conftest import DB_PATH, chat


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
    """验证结构化病历 content 字段包含期望关键词。

    The current record schema uses a single unified ``content`` field.
    All keyword expectations from the fixture are checked against it.
    """
    content = str(record.get("content") or "")

    chief_expected = expected.get("chief_complaint_contains", [])
    chief_ok = _contains_all(content, chief_expected)
    if not chief_ok and _is_ollama_provider() and "门诊" in chief_expected:
        chief_ok = any(token in content for token in ["复查", "复诊", "门诊"])
    assert chief_ok, "chief_complaint keywords missing from content: %r" % (content[:200],)
    assert _contains_any(content, expected.get("diagnosis_contains_any", [])), (
        "diagnosis keywords missing from content: %r" % (content[:200],)
    )
    assert _contains_any(content, expected.get("treatment_plan_contains_any", [])), (
        "treatment keywords missing from content: %r" % (content[:200],)
    )
    assert _contains_any(content, expected.get("auxiliary_examinations_contains_any", [])), (
        "aux exam keywords missing from content: %r" % (content[:200],)
    )
    assert _contains_any(content, expected.get("follow_up_plan_contains_any", [])), (
        "follow-up keywords missing from content: %r" % (content[:200],)
    )



@pytest.mark.integration
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["case_id"])
def test_deepseek_conversation_case_template(case: Dict):
    """Run one realistic conversation case and verify core outputs.

    Verifies:
    - API returns structured record
    - Patient row exists and has expected risk bucket
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
