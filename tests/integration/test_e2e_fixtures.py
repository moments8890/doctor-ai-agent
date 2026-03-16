"""Unified E2E test runner for all fixture files.

Runs each case through the live server, verifying:
- Patient creation and dedup
- Medical record content keywords
- Reply text keywords
- Table row counts (patients, medical_records, doctor_tasks)

How to run:
  1) Start server: cd src && uvicorn main:app --port 8001 --reload
  2) RUN_E2E_FIXTURES=1 pytest tests/integration/test_e2e_fixtures.py -v --timeout=120

Requires: running server on port 8001, Ollama on LAN.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from tests.integration.conftest import DB_PATH, chat


if os.environ.get("RUN_E2E_FIXTURES") != "1":
    pytest.skip(
        "Set RUN_E2E_FIXTURES=1 to run E2E fixture tests.",
        allow_module_level=True,
    )


ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "data"

FIXTURE_FILES = [
    "mvp_accuracy_benchmark.json",
    "deepseek_conversations_v1.json",
    "gemini_wechat_scenarios_v1.json",
]


def _load_all_cases() -> List[Dict[str, Any]]:
    cases = []
    for fname in FIXTURE_FILES:
        path = FIXTURES_DIR / fname
        if not path.exists():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        for case in raw:
            case["_source_file"] = fname
            cases.append(case)
    return cases


def _db_count(doctor_id: str, table: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE doctor_id = ?", (doctor_id,)
        ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _db_patient(doctor_id: str, name: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM patients WHERE doctor_id = ? AND name = ? ORDER BY id DESC LIMIT 1",
            (doctor_id, name),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _db_latest_record_content(doctor_id: str) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT content FROM medical_records WHERE doctor_id = ? ORDER BY id DESC LIMIT 1",
            (doctor_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _contains_any(text: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    return any(k in text for k in keywords)


ALL_CASES = _load_all_cases()


@pytest.mark.integration
@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c["case_id"])
def test_e2e_fixture(case: Dict[str, Any]):
    doctor_id = f"inttest_{case['case_id'].lower()}_{uuid.uuid4().hex[:6]}"
    chatlog = case.get("chatlog", [])
    expectations = case.get("expectations", {})

    # ── Send all turns ────────────────────────────────────────────────
    all_replies: List[str] = []
    last_data: Optional[Dict] = None

    for turn in chatlog:
        if turn.get("speaker") != "doctor":
            continue
        text = turn["text"]
        data = chat(text, doctor_id=doctor_id)
        all_replies.append(data.get("reply", ""))
        last_data = data

    joined_reply = "\n".join(all_replies)

    # ── Assert: must_not_timeout (implicit — chat() raises on timeout)

    # ── Assert: expected_patient_name ─────────────────────────────────
    expected_name = expectations.get("expected_patient_name")
    if expected_name:
        patient = _db_patient(doctor_id, expected_name)
        assert patient is not None, (
            f"[{case['case_id']}] expected patient '{expected_name}' not found in DB"
        )

    # ── Assert: expected_patient_count ────────────────────────────────
    expected_count = expectations.get("expected_patient_count")
    if expected_count is not None:
        actual = _db_count(doctor_id, "patients")
        assert actual == expected_count, (
            f"[{case['case_id']}] expected {expected_count} patients, got {actual}"
        )

    # ── Assert: expected_table_min_counts_by_doctor ───────────────────
    min_counts = expectations.get("expected_table_min_counts_by_doctor", {})
    for table, min_val in min_counts.items():
        actual = _db_count(doctor_id, table)
        assert actual >= min_val, (
            f"[{case['case_id']}] {table}: expected >= {min_val}, got {actual}"
        )

    # ── Assert: expected_table_max_counts_by_doctor ───────────────────
    max_counts = expectations.get("expected_table_max_counts_by_doctor", {})
    for table, max_val in max_counts.items():
        actual = _db_count(doctor_id, table)
        assert actual <= max_val, (
            f"[{case['case_id']}] {table}: expected <= {max_val}, got {actual}"
        )

    # ── Assert: must_include_any_of (record content keywords) ─────────
    must_include = expectations.get("must_include_any_of", [])
    if must_include:
        content = _db_latest_record_content(doctor_id) or ""
        for keyword_group in must_include:
            assert _contains_any(content, keyword_group), (
                f"[{case['case_id']}] record content missing keywords from {keyword_group}. "
                f"Content: {content[:200]}"
            )

    # ── Assert: must_include_reply_any_of (reply text keywords) ───────
    must_reply = expectations.get("must_include_reply_any_of", [])
    for keyword_group in must_reply:
        assert _contains_any(joined_reply, keyword_group), (
            f"[{case['case_id']}] reply missing keywords from {keyword_group}. "
            f"Reply: {joined_reply[:300]}"
        )
