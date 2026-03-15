"""任务管理接口自然语言端到端测试（manage/tasks APIs）。

Human-language E2E tests for manage/tasks APIs.

All scenarios start from doctor natural-language input through `/api/records/chat`,
then validate API behavior and DB persistence.
"""

from __future__ import annotations

import os
import re
import sqlite3
import uuid

import httpx
import pytest

from tests.integration.conftest import DB_PATH, SERVER, chat

_DEFAULT_VALID_WECHAT_ID = "wm80GmBgAAIQojCKNChQIjEOg5VFsgGQ"


def _latest_patient_id(doctor_id: str, patient_name: str) -> int | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM patients WHERE doctor_id=? AND name=? ORDER BY id DESC LIMIT 1",
            (doctor_id, patient_name),
        ).fetchone()
        return int(row[0]) if row else None
    finally:
        conn.close()


def _task_row(task_id: int) -> tuple | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(
            "SELECT id, status FROM doctor_tasks WHERE id=?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()


def _extract_task_id(reply: str) -> int | None:
    m = re.search(r"任务编号[：:]\s*(\d+)", reply or "")
    return int(m.group(1)) if m else None


def _run_notifier(doctor_id: str) -> dict:
    resp = httpx.post(
        f"{SERVER}/api/tasks/dev/run-notifier",
        params={"doctor_id": doctor_id},
        timeout=30,
    )
    if resp.status_code != 404:
        resp.raise_for_status()
        return resp.json()

    cfg = httpx.get(f"{SERVER}/api/admin/config", timeout=30)
    cfg.raise_for_status()
    current = cfg.json().get("config") or {}
    current["TASK_DEV_ENDPOINT_ENABLED"] = "true"

    updated = httpx.put(f"{SERVER}/api/admin/config", json={"config": current}, timeout=30)
    updated.raise_for_status()
    applied = httpx.post(f"{SERVER}/api/admin/config/apply", timeout=30)
    applied.raise_for_status()

    retry = httpx.post(
        f"{SERVER}/api/tasks/dev/run-notifier",
        params={"doctor_id": doctor_id},
        timeout=30,
    )
    if retry.status_code == 404:
        pytest.skip("Task dev notifier endpoint disabled in this environment.")
    retry.raise_for_status()
    return retry.json()


@pytest.mark.integration
def test_tasks_human_language_lifecycle_e2e():
    doctor_id = (
        os.environ.get("INTEGRATION_VALID_WECHAT_ID", _DEFAULT_VALID_WECHAT_ID).strip()
        or _DEFAULT_VALID_WECHAT_ID
    )
    patient_name = "任务患者甲"

    created = chat(f"{patient_name}，男，56岁，胸闷2天，活动后加重。", doctor_id=doctor_id)
    assert created.get("record") is not None

    scheduled = chat(
        f"给{patient_name}安排预约 2000-01-01T00:00:00",
        doctor_id=doctor_id,
    )
    assert "任务编号" in scheduled["reply"]
    task_id = _extract_task_id(scheduled["reply"])
    assert isinstance(task_id, int)

    listed = httpx.get(f"{SERVER}/api/tasks", params={"doctor_id": doctor_id}, timeout=20)
    listed.raise_for_status()
    items = listed.json()
    assert any(int(item["id"]) == task_id for item in items)

    payload = _run_notifier(doctor_id)
    due_count = int(payload["due_count"])
    sent_count = int(payload["sent_count"])
    failed_count = int(payload.get("failed_count", 0))
    assert due_count >= 1
    assert sent_count >= 1, f"expected successful notification send, got payload={payload}"
    assert failed_count == 0, f"expected zero notifier failures, got payload={payload}"

    row = _task_row(task_id)
    assert row is not None
    # notified_at column removed; notification tracking via status only

    completed = chat(f"完成 {task_id}", doctor_id=doctor_id)
    assert "已标记完成" in completed["reply"]

    pending = httpx.get(
        f"{SERVER}/api/tasks",
        params={"doctor_id": doctor_id, "status": "pending"},
        timeout=20,
    )
    pending.raise_for_status()
    assert all(int(item["id"]) != task_id for item in pending.json())

    row_after = _task_row(task_id)
    assert row_after is not None
    assert row_after[1] == "completed"


@pytest.mark.integration
def test_manage_records_and_grouped_from_human_input_e2e():
    doctor_id = f"inttest_manage_hl_{uuid.uuid4().hex[:8]}"
    p1 = "张甲"
    p2 = "李乙"

    r1 = chat(f"{p1}，男，62岁，反复胸痛3天。", doctor_id=doctor_id)
    r2 = chat(f"{p2}，女，48岁，头痛2天伴睡眠差。", doctor_id=doctor_id)
    assert r1.get("record") is not None
    assert r2.get("record") is not None

    recs = httpx.get(f"{SERVER}/api/manage/records", params={"doctor_id": doctor_id}, timeout=20)
    recs.raise_for_status()
    items = recs.json()["items"]
    assert any(item.get("patient_name") == p1 for item in items)
    assert any(item.get("patient_name") == p2 for item in items)

    grouped = httpx.get(f"{SERVER}/api/manage/patients/grouped", params={"doctor_id": doctor_id}, timeout=20)
    grouped.raise_for_status()
    groups = grouped.json()["groups"]
    total = sum(int(g["count"]) for g in groups)
    assert total >= 2

    pid = _latest_patient_id(doctor_id, p1)
    assert isinstance(pid, int)
    timeline = httpx.get(
        f"{SERVER}/api/manage/patients/{pid}/timeline",
        params={"doctor_id": doctor_id, "limit": 50},
        timeout=20,
    )
    timeline.raise_for_status()
    tdata = timeline.json()
    assert len(tdata.get("events", [])) >= 1
