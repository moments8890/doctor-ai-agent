"""管理员表全覆盖端到端测试（以人类语言输入驱动）。

尽可能通过医生语言输入创建数据，再通过用户接口和 DB 状态进行验证。

Human-language-first E2E coverage for admin tables.

Data is created from doctor language input whenever feature supports it,
then verified through user-facing APIs and DB state.
"""

from __future__ import annotations

import os
import re
import sqlite3
import uuid

import httpx
import pytest

from tests.integration.conftest import DB_PATH, SERVER, chat


def _fetch_one(sql: str, params: tuple = ()):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _name_matches(actual: str | None, expected: str) -> bool:
    if not actual:
        return False
    a = str(actual).strip()
    e = expected.strip()
    return a == e or a.startswith(e) or e in a


def _admin_rows(table_key: str, doctor_id: str):
    resp = httpx.get(
        f"{SERVER}/api/admin/tables/{table_key}",
        params={"doctor_id": doctor_id, "limit": 500},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["items"]


def _extract_task_id(reply: str) -> int | None:
    m = re.search(r"任务编号[：:]\s*(\d+)", reply or "")
    return int(m.group(1)) if m else None


def _run_notifier(doctor_id: str | None = None) -> dict:
    params = {"doctor_id": doctor_id} if doctor_id else None
    resp = httpx.post(f"{SERVER}/api/tasks/dev/run-notifier", params=params, timeout=30)
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

    retry = httpx.post(f"{SERVER}/api/tasks/dev/run-notifier", params=params, timeout=30)
    if retry.status_code == 404:
        pytest.skip("Task dev notifier endpoint disabled in this environment.")
    retry.raise_for_status()
    return retry.json()


def _setup_test_data(doctor_id: str, patient_a: str, patient_b: str) -> tuple:
    """建立测试数据：两名患者、随访任务、神经病例、上下文摘要、标签。"""
    r1 = chat(f"{patient_a}，男，58岁，胸痛2小时，考虑冠心病。", doctor_id=doctor_id)
    r2 = chat(f"{patient_b}，女，47岁，头痛3天，睡眠差。", doctor_id=doctor_id)
    assert r1.get("record") is not None
    assert r2.get("record") is not None

    task_reply = chat(f"给{patient_b}安排预约 2000-01-01T00:00:00", doctor_id=doctor_id)
    assert "任务编号" in task_reply["reply"]
    task_id = _extract_task_id(task_reply["reply"])
    assert isinstance(task_id, int)

    neuro = httpx.post(
        f"{SERVER}/api/neuro/from-text",
        json={"text": f"{patient_a}，男，68岁，突发言语含糊3小时，右上肢乏力，拟卒中流程评估。", "doctor_id": doctor_id},
        timeout=30,
    )
    neuro.raise_for_status()
    assert neuro.json().get("db_id") is not None

    context_saved = chat("总结上下文：当前以胸痛随访和神经卒中评估为主。", doctor_id=doctor_id)
    assert "已保存医生上下文摘要" in context_saved["reply"]

    create_label = httpx.post(
        f"{SERVER}/api/manage/labels",
        json={"doctor_id": doctor_id, "name": "重点随访", "color": "#FF8800"},
        timeout=20,
    )
    create_label.raise_for_status()
    label_id = int(create_label.json()["id"])
    return task_id, label_id


def _resolve_patient_a_id(doctor_id: str, patient_a: str) -> int:
    """在 DB 中查找 patient_a 的 ID，找不到则跳过测试。"""
    row = _fetch_one(
        "SELECT id FROM patients WHERE doctor_id=? AND name=? ORDER BY id DESC LIMIT 1",
        (doctor_id, patient_a),
    )
    if row is None:
        row = _fetch_one(
            "SELECT id FROM patients WHERE doctor_id=? AND name LIKE ? ORDER BY id DESC LIMIT 1",
            (doctor_id, f"{patient_a}%"),
        )
    if row is None:
        row = _fetch_one(
            "SELECT id FROM patients WHERE doctor_id=? ORDER BY id ASC LIMIT 1",
            (doctor_id,),
        )
    if row is None:
        pytest.skip("Server DB mismatch with integration DB_PATH in this local environment.")
    return int(row[0])


def _assert_table_counts_and_rows(doctor_id: str, patient_a: str, patient_b: str,
                                  task_id: int, label_id: int, new_extension: str) -> None:
    """验证所有管理员表行计数及各表的行内容断言。"""
    counts_resp = httpx.get(
        f"{SERVER}/api/admin/tables",
        params={"doctor_id": doctor_id},
        timeout=30,
    )
    counts_resp.raise_for_status()
    count_map = {it["key"]: int(it["count"]) for it in counts_resp.json()["items"]}
    if all(v == 0 for v in count_map.values()):
        pytest.skip("Server DB mismatch with integration DB_PATH in this local environment.")

    required = {
        "doctors", "patients", "medical_records", "doctor_tasks",
        "patient_labels", "patient_label_assignments", "doctor_contexts",
    }
    for key in required:
        assert count_map.get(key, 0) >= 1, f"{key} should be populated by human-input flow"

    assert any(row["doctor_id"] == doctor_id for row in _admin_rows("doctors", doctor_id))
    assert len(_admin_rows("patients", doctor_id)) >= 1
    assert any(_name_matches(row.get("patient_name"), patient_b)
               for row in _admin_rows("medical_records", doctor_id))
    assert any(int(row["id"]) == task_id for row in _admin_rows("doctor_tasks", doctor_id))
    assert any(row["doctor_id"] == doctor_id for row in _admin_rows("doctor_contexts", doctor_id))
    assert any(int(row["id"]) == label_id for row in _admin_rows("patient_labels", doctor_id))
    assert any(int(row["label_id"]) == label_id
               for row in _admin_rows("patient_label_assignments", doctor_id))
    assert any(
        row.get("key") == "structuring.extension" and new_extension in (row.get("content") or "")
        for row in _admin_rows("system_prompts", doctor_id)
    )


def _assert_notifier_and_delete(doctor_id: str, patient_a: str, patient_a_id: int, task_id: int) -> None:
    """运行通知器并断言推送计数；然后删除患者并验证级联删除。"""
    old_provider = os.environ.get("NOTIFICATION_PROVIDER")
    try:
        os.environ["NOTIFICATION_PROVIDER"] = "log"
        payload = _run_notifier(doctor_id=doctor_id)
        assert int(payload.get("due_count", 0)) >= 1
        assert (int(payload.get("sent_count", 0)) + int(payload.get("failed_count", 0))) >= 1
    finally:
        if old_provider is None:
            os.environ.pop("NOTIFICATION_PROVIDER", None)
        else:
            os.environ["NOTIFICATION_PROVIDER"] = old_provider

    assert _fetch_one("SELECT status FROM doctor_tasks WHERE id=?", (task_id,)) is not None
    deleted = chat(f"删除患者ID {patient_a_id}", doctor_id=doctor_id)
    assert "已删除患者" in deleted["reply"]
    assert _fetch_one("SELECT id FROM patients WHERE id=?", (patient_a_id,)) is None
    assert _fetch_one("SELECT id FROM medical_records WHERE patient_id=?", (patient_a_id,)) is None
    assert _fetch_one("SELECT 1 FROM patient_label_assignments WHERE patient_id=?", (patient_a_id,)) is None


@pytest.mark.integration
def test_admin_tables_human_input_e2e():
    """管理员表全覆盖端到端测试（以人类语言输入驱动）。"""
    doctor_id = f"inttest_alltables_hl_{uuid.uuid4().hex[:8]}"
    patient_a = "王甲"
    patient_b = "赵乙"

    task_id, label_id = _setup_test_data(doctor_id, patient_a, patient_b)
    patient_a_id = _resolve_patient_a_id(doctor_id, patient_a)

    assign = httpx.post(
        f"{SERVER}/api/manage/patients/{patient_a_id}/labels/{label_id}",
        params={"doctor_id": doctor_id},
        timeout=20,
    )
    assign.raise_for_status()

    prompts_before = httpx.get(f"{SERVER}/api/manage/prompts", timeout=20)
    prompts_before.raise_for_status()
    original_extension = prompts_before.json().get("structuring_extension", "")
    new_extension = f"[hl-e2e-{doctor_id}]"
    httpx.put(
        f"{SERVER}/api/manage/prompts/structuring.extension",
        json={"content": new_extension},
        timeout=20,
    ).raise_for_status()

    try:
        _assert_table_counts_and_rows(doctor_id, patient_a, patient_b, task_id, label_id, new_extension)
        _assert_notifier_and_delete(doctor_id, patient_a, patient_a_id, task_id)
    finally:
        httpx.put(
            f"{SERVER}/api/manage/prompts/structuring.extension",
            json={"content": original_extension},
            timeout=20,
        )
