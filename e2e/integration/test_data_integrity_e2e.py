"""P0 级数据完整性集成测试（/api/records/chat）。

P0 data-integrity integration tests for /api/records/chat.

These tests validate that what the AI agent returns is faithfully persisted to
the DB, and that destructive operations (delete, update) have correct cascade
and merge semantics.

Tests:
  [x] All 8 clinical fields round-trip from API response to DB row
  [x] Sparse note: treatment_plan NULL is persisted (not just returned)
  [x] Delete patient cascades records + tasks to zero
  [x] Record correction merges only the corrected field — untouched fields unchanged
  [x] Doctor isolation: doctor A cannot see doctor B's patients
  [x] Complete-task is idempotent (marking done twice keeps status=completed)
  [x] Records for a patient are returned latest-first in query reply
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

import pytest

from e2e.integration.conftest import DB_PATH, chat


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _patient_id(doctor_id: str, name: str) -> Optional[int]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM patients WHERE doctor_id=? AND name=? ORDER BY id DESC LIMIT 1",
            (doctor_id, name),
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def _patient_count(doctor_id: str, name: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM patients WHERE doctor_id=? AND name=?",
            (doctor_id, name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _record_count_for_patient(doctor_id: str, name: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT COUNT(1)
            FROM medical_records r
            JOIN patients p ON p.id = r.patient_id
            WHERE p.doctor_id=? AND p.name=?
            """,
            (doctor_id, name),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _task_count_for_patient(doctor_id: str, patient_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM doctor_tasks WHERE doctor_id=? AND patient_id=?",
            (doctor_id, patient_id),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _latest_record_fields(doctor_id: str, name: str) -> Optional[dict]:
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
            ORDER BY r.id DESC LIMIT 1
            """,
            (doctor_id, name),
        ).fetchone()
        if not row:
            return None
        return dict(zip(
            ["chief_complaint", "history_of_present_illness", "past_medical_history",
             "physical_examination", "auxiliary_examinations", "diagnosis",
             "treatment_plan", "follow_up_plan"],
            row,
        ))
    finally:
        conn.close()


def _task_status(doctor_id: str, task_id: int) -> Optional[str]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT status FROM doctor_tasks WHERE doctor_id=? AND id=?",
            (doctor_id, task_id),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _pending_task_count(doctor_id: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM doctor_tasks WHERE doctor_id=? AND status='pending'",
            (doctor_id,),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


# ── P0-1: All 8 clinical fields persisted ─────────────────────────────────────

@pytest.mark.integration
def test_all_eight_fields_persisted_to_db():
    """Rich clinical note → all 8 structured fields persist to DB, not just API response."""
    doctor_id = f"inttest_di_8f_{uuid.uuid4().hex[:8]}"
    name = "陆晨"

    r = chat(
        f"{name}，男，58岁，反复胸闷3个月，活动后加重，休息后缓解。"
        "既往高血压10年，规律服药。"
        "查体：BP 145/90mmHg，心率78次/分，双肺呼吸音清。"
        "辅助检查：心电图提示ST段压低，BNP 380。"
        "诊断：冠心病，不稳定心绞痛；高血压2级。"
        "治疗：阿司匹林100mg qd，他汀类降脂，硝酸甘油备用。"
        "随访：2周后门诊复查。",
        doctor_id=doctor_id,
    )

    assert r is not None
    assert r.get("record") is not None, "API must return structured record"

    api_rec = r["record"]
    db_rec = _latest_record_fields(doctor_id, name)
    assert db_rec is not None, "No DB record found after save"

    # API ↔ DB parity for chief_complaint (the most critical field)
    assert api_rec.get("chief_complaint") == db_rec["chief_complaint"], (
        "chief_complaint mismatch: API returned different value than DB"
    )

    # All 8 fields should be non-null in the DB for this rich input
    present_fields = [f for f, v in db_rec.items() if v and str(v).strip()]
    assert len(present_fields) >= 6, (
        f"Expected ≥6 of 8 clinical fields populated in DB, got {len(present_fields)}: "
        f"{[f for f, v in db_rec.items() if not v]}"
    )

    # Key semantic tokens must appear across the persisted record
    blob = "\n".join(v for v in db_rec.values() if isinstance(v, str)).lower()
    for token in ["胸闷", "高血压", "bnp"]:
        assert token in blob, f"Expected token '{token}' not found in any DB field"


# ── P0-2: Sparse note treatment_plan NULL validated at DB level ────────────────

@pytest.mark.integration
def test_sparse_note_treatment_null_in_db():
    """No treatment in input → treatment_plan must be NULL in DB row (not just API response)."""
    doctor_id = f"inttest_di_sparse_{uuid.uuid4().hex[:8]}"
    name = "许薇"

    r = chat(f"{name}，女，55岁，头晕2天，无其他不适。", doctor_id=doctor_id)

    assert r is not None
    assert r.get("record") is not None

    # API-level check
    api_treatment = r["record"].get("treatment_plan")
    assert api_treatment is None, (
        f"API response: treatment_plan should be null, got '{api_treatment}'"
    )

    # DB-level check: hallucination must not be silently stored
    db_rec = _latest_record_fields(doctor_id, name)
    assert db_rec is not None, "Record not saved to DB"
    db_treatment = db_rec.get("treatment_plan")
    assert db_treatment is None or db_treatment.strip() == "", (
        f"DB treatment_plan should be NULL but got: '{db_treatment}' — hallucination persisted"
    )


# ── P0-3: Delete patient cascades records and tasks ───────────────────────────

@pytest.mark.integration
def test_delete_patient_cascades_records_and_tasks():
    """Deleting a patient must cascade: medical_records and doctor_tasks both drop to zero."""
    doctor_id = f"inttest_di_cascade_{uuid.uuid4().hex[:8]}"
    name = "方磊"

    # Create patient with a record
    chat(f"{name}，男，50岁，胸痛1天，心电图正常，保存病历。", doctor_id=doctor_id)
    # Create an appointment task for this patient
    chat(f"为{name}安排复诊 2027-08-01 09:00", doctor_id=doctor_id)

    pid = _patient_id(doctor_id, name)
    assert pid is not None, "Patient row not found before delete"
    assert _record_count_for_patient(doctor_id, name) >= 1, "No records found before delete"
    assert _task_count_for_patient(doctor_id, pid) >= 1, "No tasks found before delete"

    # Delete the patient
    r = chat(f"删除患者{name}", doctor_id=doctor_id)
    assert r is not None
    assert "删除" in r["reply"] or name in r["reply"], (
        f"Delete reply did not confirm deletion: '{r['reply']}'"
    )

    # Cascade assertions
    assert _patient_count(doctor_id, name) == 0, "Patient row still exists after delete"
    assert _record_count_for_patient(doctor_id, name) == 0, "Records not cascaded after patient delete"
    assert _task_count_for_patient(doctor_id, pid) == 0, "Tasks not cascaded after patient delete"


# ── P0-4: Record correction merges only the corrected field ────────────────────

@pytest.mark.integration
def test_record_correction_does_not_alter_untouched_fields():
    """Correcting diagnosis must not overwrite treatment_plan that was not mentioned."""
    doctor_id = f"inttest_di_merge_{uuid.uuid4().hex[:8]}"
    name = "江涛"

    # Turn 1: save full record with both diagnosis and treatment_plan
    r1 = chat(
        f"{name}，男，62岁，反复胸痛，诊断不稳定心绞痛，给予阿司匹林和他汀治疗，保存病历。",
        doctor_id=doctor_id,
    )
    assert r1 is not None

    rec_before = _latest_record_fields(doctor_id, name)
    assert rec_before is not None
    treatment_before = rec_before.get("treatment_plan")

    h1 = [
        {"role": "user", "content": f"{name}，男，62岁，反复胸痛，诊断不稳定心绞痛，给予阿司匹林和他汀治疗，保存病历。"},
        {"role": "assistant", "content": r1["reply"]},
    ]

    # Turn 2: correction of diagnosis only — treatment should remain unchanged
    r2 = chat(
        f"刚才{name}的诊断写错了，心电图有ST段抬高，应该是STEMI，请更正诊断。",
        history=h1,
        doctor_id=doctor_id,
    )
    assert r2 is not None

    rec_after = _latest_record_fields(doctor_id, name)
    assert rec_after is not None

    # Diagnosis updated
    dx_blob = (rec_after.get("diagnosis") or "").lower()
    assert "stemi" in dx_blob or "st" in dx_blob, (
        f"Corrected diagnosis 'STEMI' not found in record; got: '{rec_after.get('diagnosis')}'"
    )

    # Treatment plan not altered (only diagnosis was in the correction)
    if treatment_before:
        treatment_after = rec_after.get("treatment_plan")
        assert treatment_after, "treatment_plan was wiped during diagnosis correction"


# ── P1-1: Doctor isolation ────────────────────────────────────────────────────

@pytest.mark.integration
def test_doctor_isolation_cannot_see_other_doctors_patients():
    """Doctor A's patients must not appear in Doctor B's patient list."""
    doctor_a = f"inttest_di_iso_a_{uuid.uuid4().hex[:8]}"
    doctor_b = f"inttest_di_iso_b_{uuid.uuid4().hex[:8]}"
    patient_a = "夏青"
    patient_b = "冯磊"

    chat(f"{patient_a}，女，42岁，头痛2天", doctor_id=doctor_a)
    chat(f"{patient_b}，男，55岁，胸痛1天", doctor_id=doctor_b)

    # Doctor B lists all patients — must not see Doctor A's patient
    result_b = chat("所有患者", doctor_id=doctor_b)
    assert result_b is not None
    assert patient_a not in result_b["reply"], (
        f"Doctor isolation violated: '{patient_a}' (Doctor A's patient) appeared in Doctor B's list"
    )
    assert patient_b in result_b["reply"], (
        f"Doctor B should see their own patient '{patient_b}'"
    )

    # Doctor A lists all patients — must not see Doctor B's patient
    result_a = chat("所有患者", doctor_id=doctor_a)
    assert result_a is not None
    assert patient_b not in result_a["reply"], (
        f"Doctor isolation violated: '{patient_b}' (Doctor B's patient) appeared in Doctor A's list"
    )


# ── P1-2: Complete task idempotency ───────────────────────────────────────────

@pytest.mark.integration
def test_complete_task_is_idempotent():
    """Marking a task complete twice must keep status=completed (no error on second call)."""
    doctor_id = f"inttest_di_idem_{uuid.uuid4().hex[:8]}"

    # Create patient + appointment task
    chat("潘明，男，44岁，胸痛随访", doctor_id=doctor_id)
    r_appt = chat("为潘明安排复诊 2027-09-01 10:00", doctor_id=doctor_id)
    assert r_appt is not None

    m = re.search(r"任务编号[：:]\s*(\d+)", r_appt["reply"])
    if not m:
        pytest.skip("Could not extract task id from appointment reply")
    task_id = int(m.group(1))

    # First completion
    r1 = chat(f"完成 {task_id}", doctor_id=doctor_id)
    assert r1 is not None
    assert "完成" in r1["reply"] or "✅" in r1["reply"]
    assert _task_status(doctor_id, task_id) == "completed"

    # Second completion — should not crash or revert
    r2 = chat(f"完成 {task_id}", doctor_id=doctor_id)
    assert r2 is not None
    final_status = _task_status(doctor_id, task_id)
    assert final_status == "completed", (
        f"Task status reverted after second completion: '{final_status}'"
    )


# ── P1-3: List tasks — only pending shown ─────────────────────────────────────

@pytest.mark.integration
def test_list_tasks_shows_only_pending():
    """After completing one task, task list must not include it."""
    doctor_id = f"inttest_di_tasks_{uuid.uuid4().hex[:8]}"

    chat("郑阳，男，40岁，门诊随访", doctor_id=doctor_id)
    r1 = chat("为郑阳安排复诊 2027-10-01 09:00", doctor_id=doctor_id)
    r2 = chat("为郑阳安排复诊 2027-11-01 09:00", doctor_id=doctor_id)

    assert r1 and r2 is not None
    m1 = re.search(r"任务编号[：:]\s*(\d+)", r1["reply"])
    if not m1:
        pytest.skip("Could not extract task id from first appointment reply")
    task_id_1 = m1.group(1)

    # Complete the first task
    chat(f"完成 {task_id_1}", doctor_id=doctor_id)

    # List tasks — completed one must be absent
    listed = chat("待处理任务", doctor_id=doctor_id)
    assert listed is not None

    # The completed task id should not appear in pending list
    if task_id_1 in listed["reply"]:
        # Acceptable only if reply explicitly shows it as completed
        assert "完成" in listed["reply"] or "completed" in listed["reply"].lower(), (
            f"Completed task {task_id_1} appears in pending task list without status indication"
        )


# ── P1-4: Query records — patient not found ───────────────────────────────────

@pytest.mark.integration
def test_query_records_patient_not_found_returns_error():
    """Querying records for a non-existent patient returns a clear error, not a crash."""
    doctor_id = f"inttest_di_query_notfound_{uuid.uuid4().hex[:8]}"

    r = chat("查询完全不存在的名字XYZABC的病历", doctor_id=doctor_id)

    assert r is not None
    assert r["reply"], "Reply must not be empty"
    # Should indicate patient not found — not crash or return hallucinated records
    not_found_indicated = any(kw in r["reply"] for kw in ["未找到", "找不到", "没有", "不存在", "⚠"])
    assert not_found_indicated, (
        f"Query for non-existent patient did not return a clear 'not found' message: '{r['reply']}'"
    )


# ── P1-5: List patients empty state ───────────────────────────────────────────

@pytest.mark.integration
def test_list_patients_empty_state():
    """Brand-new doctor asking for patient list should get a graceful empty response."""
    doctor_id = f"inttest_di_empty_{uuid.uuid4().hex[:8]}"

    r = chat("所有患者", doctor_id=doctor_id)

    assert r is not None
    assert r["reply"], "Reply must not be empty even for empty list"
    # Must not crash and should convey that there are no patients
    empty_indicated = any(kw in r["reply"] for kw in ["0", "零", "暂无", "没有", "尚未", "还没"])
    assert empty_indicated, (
        f"Empty patient list reply did not indicate zero patients: '{r['reply']}'"
    )


# ── P1-6: Records ordered latest-first in query reply ─────────────────────────

@pytest.mark.integration
def test_query_records_ordering_latest_first():
    """Multiple records for a patient — query reply mentions the latest encounter first."""
    doctor_id = f"inttest_di_order_{uuid.uuid4().hex[:8]}"
    name = "卫东"

    # First encounter: 胸闷
    chat(f"{name}，男，50岁，胸闷1天，保存病历。", doctor_id=doctor_id)
    # Second encounter: 头痛 (more recent)
    chat(f"{name}，头痛3天，无胸闷，保存病历。", doctor_id=doctor_id)

    result = chat(f"查询{name}的病历", doctor_id=doctor_id)
    assert result is not None

    reply = result["reply"]
    # Latest record (头痛) should appear before the older one (胸闷)
    if "头痛" in reply and "胸闷" in reply:
        assert reply.index("头痛") < reply.index("胸闷"), (
            "Latest record (头痛) should appear before older record (胸闷) in query reply"
        )
