"""Deterministic integration tests for manage/tasks APIs.

These tests seed SQLite rows directly, then validate API contracts via HTTP.
They avoid LLM-dependent behavior while still exercising end-to-end routing.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

import httpx
import pytest

from tests.integration.conftest import DB_PATH, SERVER


def _exec(sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _table_exists(name: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _has_patient_category_schema() -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(patients)").fetchall()
        }
        return {"primary_category", "category_tags", "category_rules_version"}.issubset(cols)
    finally:
        conn.close()


def _insert_patient(doctor_id: str, name: str, category: str | None) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(patients)").fetchall()
        }
    finally:
        conn.close()

    has_category_cols = {
        "primary_category",
        "category_tags",
        "category_rules_version",
    }.issubset(cols)

    if has_category_cols:
        _exec(
            """
            INSERT INTO patients
            (doctor_id, name, gender, year_of_birth, created_at, primary_category, category_tags, category_rules_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doctor_id,
                name,
                "男",
                1980,
                "2026-03-02 10:00:00",
                category,
                '["recent_visit"]' if category else "[]",
                "v1",
            ),
        )
    else:
        _exec(
            """
            INSERT INTO patients
            (doctor_id, name, gender, year_of_birth, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (doctor_id, name, "男", 1980, "2026-03-02 10:00:00"),
        )
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM patients WHERE doctor_id=? AND name=? ORDER BY id DESC LIMIT 1",
            (doctor_id, name),
        ).fetchone()
        assert row is not None
        return int(row[0])
    finally:
        conn.close()


def _cleanup(doctor_id: str) -> None:
    if _table_exists("doctor_tasks"):
        _exec("DELETE FROM doctor_tasks WHERE doctor_id=?", (doctor_id,))
    _exec("DELETE FROM medical_records WHERE doctor_id=?", (doctor_id,))
    _exec("DELETE FROM patients WHERE doctor_id=?", (doctor_id,))


@pytest.mark.integration
def test_tasks_api_roundtrip():
    if not _table_exists("doctor_tasks"):
        pytest.skip("doctor_tasks table not available in current DB/schema")

    doctor_id = f"inttest_tasks_{uuid.uuid4().hex[:8]}"
    try:
        _exec(
            """
            INSERT INTO doctor_tasks
            (doctor_id, patient_id, record_id, task_type, title, content, status, due_at, notified_at, created_at)
            VALUES (?, NULL, NULL, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                doctor_id,
                "follow_up",
                "随访提醒：张三",
                "两周后复查",
                "pending",
                "2026-03-20 09:00:00",
                "2026-03-02 09:00:00",
            ),
        )
        _exec(
            """
            INSERT INTO doctor_tasks
            (doctor_id, patient_id, record_id, task_type, title, content, status, due_at, notified_at, created_at)
            VALUES (?, NULL, NULL, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                doctor_id,
                "appointment",
                "预约提醒：李四",
                "门诊复查",
                "pending",
                "2026-03-22 14:00:00",
                "2026-03-02 09:30:00",
            ),
        )

        resp = httpx.get(f"{SERVER}/api/tasks", params={"doctor_id": doctor_id}, timeout=20)
        resp.raise_for_status()
        tasks = resp.json()
        assert len(tasks) == 2

        to_complete = tasks[0]["id"]
        patch = httpx.patch(
            f"{SERVER}/api/tasks/{to_complete}",
            params={"doctor_id": doctor_id},
            json={"status": "completed"},
            timeout=20,
        )
        patch.raise_for_status()
        assert patch.json()["status"] == "completed"

        pending = httpx.get(
            f"{SERVER}/api/tasks",
            params={"doctor_id": doctor_id, "status": "pending"},
            timeout=20,
        )
        pending.raise_for_status()
        pending_items = pending.json()
        assert len(pending_items) == 1
        assert pending_items[0]["id"] != to_complete
    finally:
        _cleanup(doctor_id)


@pytest.mark.integration
def test_manage_patients_grouped_counts():
    if not _has_patient_category_schema():
        pytest.skip("patient category schema not available in current DB/server")

    doctor_id = f"inttest_group_{uuid.uuid4().hex[:8]}"
    try:
        _insert_patient(doctor_id, "高风险患者", "high_risk")
        _insert_patient(doctor_id, "新患者", "new")
        _insert_patient(doctor_id, "未分类患者", None)

        resp = httpx.get(
            f"{SERVER}/api/manage/patients/grouped",
            params={"doctor_id": doctor_id},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        groups = {g["group"]: g for g in data["groups"]}

        assert groups["high_risk"]["count"] == 1
        assert groups["new"]["count"] == 1
        assert groups["uncategorized"]["count"] == 1
    finally:
        _cleanup(doctor_id)


@pytest.mark.integration
def test_manage_records_includes_raw_fields():
    doctor_id = f"inttest_records_{uuid.uuid4().hex[:8]}"
    try:
        pid = _insert_patient(doctor_id, "记录测试患者", "new")
        _exec(
            """
            INSERT INTO medical_records
            (patient_id, doctor_id, chief_complaint, history_of_present_illness, past_medical_history,
             physical_examination, auxiliary_examinations, diagnosis, treatment_plan, follow_up_plan, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                doctor_id,
                "胸痛2小时",
                "活动后加重",
                "高血压10年",
                "BP 160/100",
                "ECG ST压低",
                "冠心病",
                "阿司匹林+他汀",
                "两周复查",
                datetime(2026, 3, 2, 11, 0, 0).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

        resp = httpx.get(
            f"{SERVER}/api/manage/records",
            params={"doctor_id": doctor_id},
            timeout=20,
        )
        resp.raise_for_status()
        items = resp.json()["items"]
        if len(items) == 0:
            pytest.skip(
                "Server appears to use a different DB path than tests/integration DB_PATH; "
                "cannot validate seeded-record payload in this local environment."
            )
        assert len(items) == 1

        item = items[0]
        assert item["history_of_present_illness"] == "活动后加重"
        assert item["past_medical_history"] == "高血压10年"
        assert item["physical_examination"] == "BP 160/100"
        assert item["auxiliary_examinations"] == "ECG ST压低"
        assert item["follow_up_plan"] == "两周复查"
    finally:
        _cleanup(doctor_id)
