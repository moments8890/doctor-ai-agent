"""Real-world doctor↔agent text E2E scenarios.

These tests exercise realistic input styles against `/api/records/chat`:
- verbose dictation
- terse notes
- multi-line fragmented notes
- typo/noisy input
- mixed Chinese + medical abbreviations (STEMI/BNP/PCI/EF)
- multi-turn clarification when patient name is omitted

Validation is DB-backed whenever possible:
- patient row exists
- record row exists
- API payload and DB row are consistent for key fields
- sparse/no-treatment notes do not fabricate treatment plans
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Dict, List, Optional, Tuple

import pytest

from tests.integration.conftest import DB_PATH, chat
from tests.fixtures.realworld_cases import REALWORLD_SCENARIOS


def _latest_patient_id(doctor_id: str, patient_name: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM patients WHERE doctor_id=? AND name=? ORDER BY id DESC LIMIT 1",
            (doctor_id, patient_name),
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def _patient_count(doctor_id: str, patient_name: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM patients WHERE doctor_id=? AND name=?",
            (doctor_id, patient_name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _record_count_for_patient(doctor_id: str, patient_name: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT COUNT(1)
            FROM medical_records r
            JOIN patients p ON p.id = r.patient_id
            WHERE p.doctor_id=? AND p.name=?
            """,
            (doctor_id, patient_name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _latest_record_for_patient(doctor_id: str, patient_name: str) -> Optional[Dict[str, Optional[str]]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT r.chief_complaint,
                   r.history_of_present_illness,
                   r.past_medical_history,
                   r.physical_examination,
                   r.auxiliary_examinations,
                   r.diagnosis,
                   r.treatment_plan,
                   r.follow_up_plan
            FROM medical_records r
            JOIN patients p ON p.id = r.patient_id
            WHERE p.doctor_id=? AND p.name=?
            ORDER BY r.id DESC
            LIMIT 1
            """,
            (doctor_id, patient_name),
        ).fetchone()
        if not row:
            return None
        keys = [
            "chief_complaint",
            "history_of_present_illness",
            "past_medical_history",
            "physical_examination",
            "auxiliary_examinations",
            "diagnosis",
            "treatment_plan",
            "follow_up_plan",
        ]
        return dict(zip(keys, row))
    finally:
        conn.close()


def _record_text_blob(record: Dict[str, Optional[str]]) -> str:
    return "\n".join([v for v in record.values() if isinstance(v, str)]).lower()


@pytest.mark.integration
@pytest.mark.parametrize(
    "case_id,patient_name,input_text,expected_tokens,expect_no_treatment",
    REALWORLD_SCENARIOS,
)
def test_realworld_note_styles_db_correctness(
    case_id: str,
    patient_name: str,
    input_text: str,
    expected_tokens: List[str],
    expect_no_treatment: bool,
):
    """Many real-world note styles should persist correctly and consistently."""
    doctor_id = "inttest_rw_matrix_{0}_{1}".format(case_id, uuid.uuid4().hex[:8])

    response = chat(input_text, doctor_id=doctor_id)

    assert response.get("record") is not None, "API must return a structured record"
    assert response["record"].get("chief_complaint"), "chief_complaint must not be empty"

    pid = _latest_patient_id(doctor_id, patient_name)
    assert pid is not None, "Patient row missing for case={0}".format(case_id)

    db_rec = _latest_record_for_patient(doctor_id, patient_name)
    assert db_rec is not None, "DB record missing for case={0}".format(case_id)

    # API payload and DB persistence should align on key field.
    assert response["record"]["chief_complaint"] == db_rec["chief_complaint"]

    blob = _record_text_blob(db_rec)
    for token in expected_tokens:
        assert token.lower() in blob, (
            "Expected token '{0}' not found in persisted record for case={1}".format(token, case_id)
        )

    treatment = db_rec.get("treatment_plan")
    if expect_no_treatment:
        assert treatment is None or treatment.strip() == "", (
            "Unexpected treatment hallucination for sparse case={0}: {1}".format(case_id, treatment)
        )


@pytest.mark.integration
def test_realworld_multi_turn_followup_and_dedup_flow():
    """End-to-end conversation flow with clarification, follow-up, query, and list."""
    doctor_id = "inttest_rw_convo_{0}".format(uuid.uuid4().hex[:8])

    # Turn 1: missing name should trigger clarification.
    first = chat("突发胸痛两小时，伴大汗、恶心", doctor_id=doctor_id)
    assert "名字" in first["reply"]
    assert first["record"] is None

    # Turn 2: provide only patient name using history context.
    history = [
        {"role": "user", "content": "突发胸痛两小时，伴大汗、恶心"},
        {"role": "assistant", "content": first["reply"]},
    ]
    second = chat("沈卓", history=history, doctor_id=doctor_id)
    assert second["record"] is not None

    # Turn 3: concise follow-up for same patient should append record (not new patient row).
    third = chat("沈卓，今日胸闷较前缓解，继续当前方案，三天后复查", doctor_id=doctor_id)
    assert third["record"] is not None

    assert _patient_count(doctor_id, "沈卓") == 1
    assert _record_count_for_patient(doctor_id, "沈卓") >= 2

    # Turn 4: create second patient via short style.
    fourth = chat("顾帆，女，49岁，心悸半天", doctor_id=doctor_id)
    assert fourth["record"] is not None

    # Turn 5: query one patient's history should be human-readable and include key sections.
    query = chat("查询沈卓的病历", doctor_id=doctor_id)
    assert "患者【沈卓】最近" in query["reply"]
    assert "主诉" in query["reply"]

    # Turn 6: list should include both names.
    listed = chat("所有患者", doctor_id=doctor_id)
    assert "沈卓" in listed["reply"]
    assert "顾帆" in listed["reply"]


@pytest.mark.integration
def test_realworld_multi_input_fragmented_dictation_keeps_context():
    """Doctor sends fragmented multi-input dictation; final record should still persist."""
    doctor_id = "inttest_rw_multi_{0}".format(uuid.uuid4().hex[:8])

    # Simulate fragmented dictation across multiple turns while keeping patient
    # name explicit each turn for deterministic persistence.
    h0 = []
    r1 = chat("陆衡，男，57岁，胸闷反复1周", history=h0, doctor_id=doctor_id)
    assert r1.get("record") is not None

    h1 = [
        {"role": "user", "content": "陆衡，男，57岁，胸闷反复1周"},
        {"role": "assistant", "content": r1["reply"]},
    ]
    r2 = chat("陆衡，昨夜加重，伴气短", history=h1, doctor_id=doctor_id)
    assert r2.get("record") is not None

    h2 = h1 + [
        {"role": "user", "content": "陆衡，昨夜加重，伴气短"},
        {"role": "assistant", "content": r2["reply"]},
    ]
    r3 = chat("陆衡，BNP升高，建议复查", history=h2, doctor_id=doctor_id)
    assert r3.get("record") is not None

    # Final DB assertions.
    rec = _latest_record_for_patient(doctor_id, "陆衡")
    assert rec is not None, "Fragmented multi-input flow did not persist any record"
    assert rec.get("chief_complaint")
    assert _record_count_for_patient(doctor_id, "陆衡") >= 3

    blob = _record_text_blob(rec)
    assert "胸闷" in blob or "气短" in blob or "bnp" in blob
