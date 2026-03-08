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
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pytest

from e2e.integration.conftest import DB_PATH, chat
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
    matched = [token for token in expected_tokens if token.lower() in blob]
    required_hits = len(expected_tokens)
    assert len(matched) >= required_hits, (
        "Insufficient token coverage for case={0}; matched={1}/{2}; missing={3}".format(
            case_id,
            len(matched),
            len(expected_tokens),
            [token for token in expected_tokens if token not in matched],
        )
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


# ─────────────────────────────────────────────────────────────────────────────
# Correction / update flows — DB-level assertions on corrected values
# ─────────────────────────────────────────────────────────────────────────────

def _patient_gender(doctor_id: str, patient_name: str) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT gender FROM patients WHERE doctor_id=? AND name=? ORDER BY id DESC LIMIT 1",
            (doctor_id, patient_name),
        ).fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        conn.close()


@pytest.mark.integration
def test_correction_gender_overrides_initial_dictation():
    """Doctor initially dictates wrong gender, then corrects it.
    Expectation: DB patient row reflects the corrected gender, not the original."""
    doctor_id = "inttest_corr_gender_{0}".format(uuid.uuid4().hex[:8])
    patient_name = "张晴"

    # Turn 1 — wrong gender (male for a female patient)
    r1 = chat("张晴，男，35岁，头痛2天，睡眠差。", doctor_id=doctor_id)
    assert r1 is not None

    h1 = [
        {"role": "user", "content": "张晴，男，35岁，头痛2天，睡眠差。"},
        {"role": "assistant", "content": r1["reply"]},
    ]

    # Turn 2 — explicit gender correction
    r2 = chat(
        "等等，张晴是女性，刚才性别说错了，请更正为女。",
        history=h1,
        doctor_id=doctor_id,
    )
    assert r2 is not None

    h2 = h1 + [
        {"role": "user", "content": "等等，张晴是女性，刚才性别说错了，请更正为女。"},
        {"role": "assistant", "content": r2["reply"]},
    ]

    # Turn 3 — explicit save with corrected demographics
    r3 = chat(
        "张晴，女，35岁，头痛2天，睡眠差，请保存病历。",
        history=h2,
        doctor_id=doctor_id,
    )
    assert r3 is not None

    # DB assertion: gender should be 女, not 男
    gender = _patient_gender(doctor_id, patient_name)
    assert gender is not None, "Patient row not created for {0}".format(patient_name)
    assert gender == "女", (
        "Expected corrected gender '女', got '{0}' — correction was not applied".format(gender)
    )


@pytest.mark.integration
def test_correction_chief_complaint_overrides_initial():
    """Doctor initially dictates wrong chief complaint, then corrects it.
    Expectation: final medical record contains the corrected complaint, not the original."""
    doctor_id = "inttest_corr_cc_{0}".format(uuid.uuid4().hex[:8])
    patient_name = "李波"

    # Turn 1 — wrong chief complaint (胸闷 instead of 胸痛)
    r1 = chat("李波，男，52岁，主诉胸闷3天，活动后加重。", doctor_id=doctor_id)
    assert r1 is not None

    h1 = [
        {"role": "user", "content": "李波，男，52岁，主诉胸闷3天，活动后加重。"},
        {"role": "assistant", "content": r1["reply"]},
    ]

    # Turn 2 — correction: 胸痛, not 胸闷
    r2 = chat(
        "不对，李波的主诉是胸痛，不是胸闷，请帮我更正。",
        history=h1,
        doctor_id=doctor_id,
    )
    assert r2 is not None

    h2 = h1 + [
        {"role": "user", "content": "不对，李波的主诉是胸痛，不是胸闷，请帮我更正。"},
        {"role": "assistant", "content": r2["reply"]},
    ]

    # Turn 3 — save with corrected chief complaint
    r3 = chat(
        "确认患者李波，主诉胸痛，请建档并保存本次病历。",
        history=h2,
        doctor_id=doctor_id,
    )
    assert r3 is not None

    rec = _latest_record_for_patient(doctor_id, patient_name)
    assert rec is not None, "Medical record missing for {0}".format(patient_name)

    blob = _record_text_blob(rec)
    assert "胸痛" in blob, (
        "Corrected chief complaint '胸痛' not found in DB record for {0}".format(patient_name)
    )


@pytest.mark.integration
def test_addendum_supplements_initial_sparse_record():
    """Doctor adds supplemental symptoms after the initial sparse note.
    Expectation: final record contains both the original and the added information."""
    doctor_id = "inttest_addendum_{0}".format(uuid.uuid4().hex[:8])
    patient_name = "孙明"

    # Turn 1 — sparse initial note
    r1 = chat("孙明，男，48岁，头痛2天。", doctor_id=doctor_id)
    assert r1 is not None

    h1 = [
        {"role": "user", "content": "孙明，男，48岁，头痛2天。"},
        {"role": "assistant", "content": r1["reply"]},
    ]

    # Turn 2 — addendum with additional symptoms
    r2 = chat(
        "补充一下：还有恶心和发热38.5℃，昨晚畏光明显。",
        history=h1,
        doctor_id=doctor_id,
    )
    assert r2 is not None

    h2 = h1 + [
        {"role": "user", "content": "补充一下：还有恶心和发热38.5℃，昨晚畏光明显。"},
        {"role": "assistant", "content": r2["reply"]},
    ]

    # Turn 3 — save with combined info
    r3 = chat(
        "孙明，头痛伴恶心发热，请建档并保存本次病历。",
        history=h2,
        doctor_id=doctor_id,
    )
    assert r3 is not None

    rec = _latest_record_for_patient(doctor_id, patient_name)
    assert rec is not None, "Medical record missing for {0}".format(patient_name)

    blob = _record_text_blob(rec)
    assert "头痛" in blob, "Original symptom '头痛' missing after addendum"
    supplemental_found = any(kw in blob for kw in ["恶心", "发热", "38", "畏光"])
    assert supplemental_found, (
        "Supplemental info (恶心/发热/畏光) not found in record — addendum was dropped"
    )


@pytest.mark.integration
def test_correction_vital_signs_replaced():
    """Doctor dictates wrong blood pressure, then corrects it.
    Expectation: the corrected BP value (170/105) appears in the DB record,
    not the originally stated wrong value (150/90)."""
    doctor_id = "inttest_corr_vitals_{0}".format(uuid.uuid4().hex[:8])
    patient_name = "吴强"

    # Turn 1 — wrong BP reading
    r1 = chat(
        "吴强，男，63岁，高血压门诊随访，血压150/90mmHg，心率80次/分。",
        doctor_id=doctor_id,
    )
    assert r1 is not None

    h1 = [
        {"role": "user", "content": "吴强，男，63岁，高血压门诊随访，血压150/90mmHg，心率80次/分。"},
        {"role": "assistant", "content": r1["reply"]},
    ]

    # Turn 2 — correct the BP
    r2 = chat(
        "血压读错了，实际是170/105，请更正。",
        history=h1,
        doctor_id=doctor_id,
    )
    assert r2 is not None

    h2 = h1 + [
        {"role": "user", "content": "血压读错了，实际是170/105，请更正。"},
        {"role": "assistant", "content": r2["reply"]},
    ]

    # Turn 3 — save with corrected BP
    r3 = chat(
        "确认患者吴强，血压170/105，高血压，请建档并保存本次病历。",
        history=h2,
        doctor_id=doctor_id,
    )
    assert r3 is not None

    rec = _latest_record_for_patient(doctor_id, patient_name)
    assert rec is not None, "Medical record missing for {0}".format(patient_name)

    blob = _record_text_blob(rec)
    assert "170" in blob, (
        "Corrected BP '170/105' not found in DB record — vital sign correction was not applied"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Update existing patient / record — DB-level assertions
# ─────────────────────────────────────────────────────────────────────────────

def _patient_year_of_birth(doctor_id: str, patient_name: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT year_of_birth FROM patients WHERE doctor_id=? AND name=? ORDER BY id DESC LIMIT 1",
            (doctor_id, patient_name),
        ).fetchone()
        return int(row[0]) if row and row[0] else None
    finally:
        conn.close()


def _latest_record_blob(doctor_id: str, patient_name: str) -> str:
    rec = _latest_record_for_patient(doctor_id, patient_name)
    return _record_text_blob(rec) if rec else ""


@pytest.mark.integration
def test_update_patient_age_via_direct_command():
    """Doctor uses a direct update command to fix a wrong age.
    Expectation: patients.year_of_birth updated, no new patient row created."""
    doctor_id = "inttest_upd_age_{0}".format(uuid.uuid4().hex[:8])
    patient_name = "王明"

    # Turn 1: initial record with wrong age (40)
    r1 = chat("王明，男，40岁，高血压门诊就诊，血压145/90，保存病历。", doctor_id=doctor_id)
    assert r1 is not None

    yob_before = _patient_year_of_birth(doctor_id, patient_name)
    assert yob_before is not None, "Patient row not created"
    _current_year = datetime.now().year
    # year_of_birth should be roughly current_year - 40
    assert abs(yob_before - (_current_year - 40)) <= 1

    # Turn 2: direct age correction command
    r2 = chat("修改王明的年龄为50岁", doctor_id=doctor_id)
    assert r2 is not None

    yob_after = _patient_year_of_birth(doctor_id, patient_name)
    assert yob_after is not None
    assert abs(yob_after - (_current_year - 50)) <= 1, (
        "Expected year_of_birth ~{0}, got {1}".format(_current_year - 50, yob_after)
    )
    # Still exactly 1 patient row
    assert _patient_count(doctor_id, patient_name) == 1


@pytest.mark.integration
def test_update_patient_gender_via_direct_command():
    """Doctor uses a direct update command to fix gender — no new record created."""
    doctor_id = "inttest_upd_gender2_{0}".format(uuid.uuid4().hex[:8])
    patient_name = "李华"

    # Turn 1: initial record with wrong gender (男 for a female patient)
    r1 = chat("李华，男，28岁，发热3天，保存病历。", doctor_id=doctor_id)
    assert r1 is not None
    assert _patient_gender(doctor_id, patient_name) == "男"

    # Turn 2: direct gender correction
    r2 = chat("更新李华的性别为女", doctor_id=doctor_id)
    assert r2 is not None

    gender_after = _patient_gender(doctor_id, patient_name)
    assert gender_after == "女", (
        "Expected gender 女 after update command, got {0}".format(gender_after)
    )
    # No new patient row or record row should be created
    assert _patient_count(doctor_id, patient_name) == 1


@pytest.mark.integration
def test_correct_previous_record_no_duplicate_created():
    """Correcting a record must UPDATE in-place — no extra record row inserted."""
    doctor_id = "inttest_corr_nodup_{0}".format(uuid.uuid4().hex[:8])
    patient_name = "李波"

    # Turn 1: save initial record with wrong chief complaint (胸闷 instead of 胸痛)
    r1 = chat("李波，男，52岁，主诉胸闷3天，活动后加重，保存病历。", doctor_id=doctor_id)
    assert r1 is not None

    count_before = _record_count_for_patient(doctor_id, patient_name)
    assert count_before >= 1

    h1 = [
        {"role": "user", "content": "李波，男，52岁，主诉胸闷3天，活动后加重，保存病历。"},
        {"role": "assistant", "content": r1["reply"]},
    ]

    # Turn 2: correction command — should update the existing record, not add a new one
    r2 = chat(
        "刚才李波的主诉写错了，应该是胸痛不是胸闷，请更正。",
        history=h1,
        doctor_id=doctor_id,
    )
    assert r2 is not None

    count_after = _record_count_for_patient(doctor_id, patient_name)
    assert count_after == count_before, (
        "Record correction must not create duplicates: expected {0} record(s), got {1}".format(
            count_before, count_after
        )
    )

    blob = _latest_record_blob(doctor_id, patient_name)
    assert "胸痛" in blob, (
        "Corrected chief complaint '胸痛' not found in record after correction"
    )


@pytest.mark.integration
def test_correct_previous_record_diagnosis_in_place():
    """Doctor corrects a diagnosis on the latest record — still one record, updated dx."""
    doctor_id = "inttest_corr_dx_{0}".format(uuid.uuid4().hex[:8])
    patient_name = "陈刚"

    # Turn 1: initial record with preliminary diagnosis
    r1 = chat(
        "陈刚，男，60岁，反复胸痛，初步诊断不稳定心绞痛，保存病历。",
        doctor_id=doctor_id,
    )
    assert r1 is not None

    count_before = _record_count_for_patient(doctor_id, patient_name)
    assert count_before >= 1

    h1 = [
        {"role": "user", "content": "陈刚，男，60岁，反复胸痛，初步诊断不稳定心绞痛，保存病历。"},
        {"role": "assistant", "content": r1["reply"]},
    ]

    # Turn 2: diagnosis correction — new ECG shows STEMI
    r2 = chat(
        "刚才陈刚的诊断写错了，心电图有ST段抬高，应更正诊断为STEMI，请更正上一条病历。",
        history=h1,
        doctor_id=doctor_id,
    )
    assert r2 is not None

    count_after = _record_count_for_patient(doctor_id, patient_name)
    assert count_after == count_before, (
        "Diagnosis correction must not create a new record: expected {0}, got {1}".format(
            count_before, count_after
        )
    )

    blob = _latest_record_blob(doctor_id, patient_name)
    assert "stemi" in blob or "ST" in blob, (
        "Corrected diagnosis 'STEMI' not found in record after correction"
    )


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
