"""LLM-backed E2E tests for patient portal chat triage.

These tests exercise the live ``/api/patient/chat`` endpoint against a running
server on port 8001. They encode the architecture contract from
``docs/architecture.md``:

- patient chat auto-replies should use Layer 5 patient context
- escalation summaries should preserve relevant prior patient history

The current implementation is expected to fail the history-aware assertions
because ``load_patient_context()`` does not yet load prior structured records.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List

import httpx
import pytest

from tests.integration.conftest import DB_PATH, SERVER

if os.environ.get("RUN_E2E_FIXTURES") != "1":
    pytest.skip(
        "Set RUN_E2E_FIXTURES=1 to run patient chat LLM E2E tests.",
        allow_module_level=True,
    )


TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

pytestmark = [pytest.mark.integration]


def _setup_doctor(doctor_id: str, name: str = "测试医生") -> None:
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO doctors (doctor_id, name, specialty, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (doctor_id, name, "neurology", now, now),
        )
        conn.commit()
    finally:
        conn.close()


def _register_patient(
    doctor_id: str,
    name: str,
    gender: str = "女",
    year_of_birth: int = 1988,
) -> Dict[str, Any]:
    phone = "139{0}".format(uuid.uuid4().hex[:8])
    resp = httpx.post(
        "{0}/api/patient/register".format(SERVER),
        json={
            "doctor_id": doctor_id,
            "name": name,
            "gender": gender,
            "year_of_birth": year_of_birth,
            "phone": phone,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    body["phone"] = phone
    return body


def _post_chat(token: str, text: str) -> httpx.Response:
    return httpx.post(
        "{0}/api/patient/chat".format(SERVER),
        json={"text": text},
        headers={"Authorization": "Bearer {0}".format(token)},
        timeout=TIMEOUT,
    )


def _seed_prior_record(
    doctor_id: str,
    patient_id: int,
    *,
    content: str,
    past_history: str = "",
    allergy_history: str = "",
    diagnosis: str = "",
    treatment_plan: str = "",
    orders_followup: str = "",
    status: str = "completed",
) -> None:
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO medical_records (
                patient_id, doctor_id, record_type, content, created_at, updated_at, status,
                chief_complaint, present_illness, past_history, allergy_history,
                diagnosis, treatment_plan, orders_followup
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                doctor_id,
                "visit",
                content,
                now,
                now,
                status,
                "复诊",
                "随访咨询",
                past_history,
                allergy_history,
                diagnosis,
                treatment_plan,
                orders_followup,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_chat_rows(patient_id: int, doctor_id: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, content, direction, source, triage_category, structured_data, ai_handled
            FROM patient_messages
            WHERE patient_id = ? AND doctor_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (patient_id, doctor_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _cleanup(doctor_id: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        patient_rows = conn.execute(
            "SELECT id FROM patients WHERE doctor_id = ?",
            (doctor_id,),
        ).fetchall()
        patient_ids = [row[0] for row in patient_rows]

        if patient_ids:
            conn.executemany(
                "DELETE FROM message_drafts WHERE patient_id = ?",
                [(str(patient_id),) for patient_id in patient_ids],
            )
            conn.executemany(
                "DELETE FROM patient_messages WHERE patient_id = ?",
                [(patient_id,) for patient_id in patient_ids],
            )
            conn.executemany(
                "DELETE FROM patient_auth WHERE patient_id = ?",
                [(patient_id,) for patient_id in patient_ids],
            )
            conn.executemany(
                "DELETE FROM medical_records WHERE patient_id = ?",
                [(patient_id,) for patient_id in patient_ids],
            )

        conn.execute(
            "DELETE FROM doctor_knowledge_items WHERE doctor_id = ?",
            (doctor_id,),
        )
        conn.execute(
            "DELETE FROM patients WHERE doctor_id = ?",
            (doctor_id,),
        )
        conn.execute(
            "DELETE FROM doctors WHERE doctor_id = ?",
            (doctor_id,),
        )
        conn.commit()
    finally:
        conn.close()


def _parse_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("structured_data") or "{}"
    return json.loads(raw)


def _assert_two_message_flow(rows: List[Dict[str, Any]]) -> None:
    assert len(rows) == 2, "Expected one inbound patient message and one outbound AI message, got: {0}".format(rows)
    assert rows[0]["direction"] == "inbound", rows
    assert rows[0]["source"] == "patient", rows
    assert rows[1]["direction"] == "outbound", rows
    assert rows[1]["source"] == "ai", rows


def _outbound_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row["direction"] == "outbound"]


def _inbound_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row["direction"] == "inbound"]


def test_patient_chat_auto_reply_should_use_prior_allergy_history_e2e():
    """Architecture contract: informational auto-replies should see prior history."""
    doctor_id = "inttest_chatinfo_{0}".format(uuid.uuid4().hex[:8])
    _setup_doctor(doctor_id)

    try:
        reg = _register_patient(doctor_id, name="过敏史患者")
        patient_id = reg["patient_id"]
        token = reg["token"]

        _seed_prior_record(
            doctor_id,
            patient_id,
            content="患者既往明确磺胺类药物过敏，术后复诊稳定。",
            past_history="2025年行动脉瘤弹簧圈栓塞术。",
            allergy_history="磺胺类药物过敏。",
            diagnosis="颅内动脉瘤术后随访。",
        )

        resp = _post_chat(token, "我之前记录的是对什么药过敏？")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["triage_category"] == "informational", body
        assert body["ai_handled"] is True, body

        rows = _fetch_chat_rows(patient_id, doctor_id)
        _assert_two_message_flow(rows)
        assert rows[0]["triage_category"] == "informational", rows
        assert rows[1]["triage_category"] == "informational", rows

        assert "磺胺" in body["reply"], (
            "docs/architecture.md says patient chat should use Layer 5 patient context "
            "('patient records/state'). The seeded allergy history was not reflected in "
            "the live AI auto-reply: {0}".format(body["reply"])
        )
    finally:
        _cleanup(doctor_id)


def test_patient_chat_escalation_persists_summary_and_ack_e2e():
    """Escalation path should save structured summary + AI acknowledgment."""
    doctor_id = "inttest_chatesc_{0}".format(uuid.uuid4().hex[:8])
    _setup_doctor(doctor_id)

    try:
        reg = _register_patient(doctor_id, name="头痛加重患者")
        patient_id = reg["patient_id"]
        token = reg["token"]

        resp = _post_chat(token, "头痛比昨天严重了，吃止疼药也不管用")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["triage_category"] != "informational", body
        assert body["ai_handled"] is False, body
        assert "医生" in body["reply"], body

        rows = _fetch_chat_rows(patient_id, doctor_id)
        _assert_two_message_flow(rows)

        inbound = rows[0]
        outbound = rows[1]
        assert inbound["triage_category"] == body["triage_category"], rows
        assert inbound["ai_handled"] in (0, False, None), rows
        assert inbound["structured_data"], rows

        summary = _parse_summary(inbound)
        assert summary.get("patient_question"), summary
        assert summary.get("reason_for_escalation"), summary
        assert summary.get("suggested_action"), summary

        assert outbound["triage_category"] == body["triage_category"], rows
        assert outbound["ai_handled"] in (0, False, None), rows
    finally:
        _cleanup(doctor_id)


def test_patient_chat_escalation_summary_should_include_prior_postop_history_e2e():
    """Architecture contract: escalation summaries should preserve prior history."""
    doctor_id = "inttest_chatctx_{0}".format(uuid.uuid4().hex[:8])
    _setup_doctor(doctor_id)

    try:
        reg = _register_patient(doctor_id, name="术后随访患者")
        patient_id = reg["patient_id"]
        token = reg["token"]

        _seed_prior_record(
            doctor_id,
            patient_id,
            content="患者2025年12月行颅内动脉瘤弹簧圈栓塞术后复诊，恢复平稳。",
            past_history="2025年12月行颅内动脉瘤弹簧圈栓塞术。",
            diagnosis="颅内动脉瘤弹簧圈栓塞术后恢复期。",
            orders_followup="1个月后复查CTA。",
        )

        resp = _post_chat(token, "头痛比昨天严重了，吃止疼药也不管用")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["triage_category"] != "informational", body
        assert body["ai_handled"] is False, body

        rows = _fetch_chat_rows(patient_id, doctor_id)
        _assert_two_message_flow(rows)

        inbound = rows[0]
        summary = _parse_summary(inbound)
        summary_text = json.dumps(summary, ensure_ascii=False)

        assert ("弹簧圈" in summary_text) or ("动脉瘤术后" in summary_text), (
            "docs/architecture.md says Layer 5 patient context includes patient records/state, "
            "so the doctor-facing escalation summary should carry forward the seeded postop "
            "history. Current summary ignored that history: {0}".format(summary_text)
        )
    finally:
        _cleanup(doctor_id)


def test_patient_chat_ambiguous_short_message_escalates_safely_e2e():
    """Short ambiguous messages should route to a safe doctor-reviewed path."""
    doctor_id = "inttest_chatshort_{0}".format(uuid.uuid4().hex[:8])
    _setup_doctor(doctor_id)

    try:
        reg = _register_patient(doctor_id, name="模糊消息患者")
        patient_id = reg["patient_id"]
        token = reg["token"]

        resp = _post_chat(token, "我想问个问题但不知道怎么说")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["triage_category"] != "informational", body
        assert body["ai_handled"] is False, body
        assert "医生" in body["reply"], body

        rows = _fetch_chat_rows(patient_id, doctor_id)
        _assert_two_message_flow(rows)

        inbound = rows[0]
        assert inbound["structured_data"], rows
        summary = _parse_summary(inbound)
        assert summary.get("reason_for_escalation"), summary
    finally:
        _cleanup(doctor_id)


def test_patient_chat_long_mixed_message_prioritizes_clinical_content_e2e():
    """Long messages with symptoms plus info requests must stay on the clinical path."""
    doctor_id = "inttest_chatlong_{0}".format(uuid.uuid4().hex[:8])
    _setup_doctor(doctor_id)

    try:
        reg = _register_patient(doctor_id, name="长消息患者")
        patient_id = reg["patient_id"]
        token = reg["token"]

        message = (
            "医生您好，我想问一下阿司匹林到底是饭前还是饭后吃。"
            "另外我这两天头晕比前几天厉害，今天早上起来还有点恶心，"
            "站久了发飘，午饭后也不太舒服。我没有胸痛，也没有喘不上气，"
            "但就是觉得和之前不一样，所以想一起问问是不是药物的问题。"
        )
        resp = _post_chat(token, message)
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["triage_category"] != "informational", body
        assert body["ai_handled"] is False, body

        rows = _fetch_chat_rows(patient_id, doctor_id)
        _assert_two_message_flow(rows)
        summary = _parse_summary(rows[0])
        summary_text = json.dumps(summary, ensure_ascii=False)
        assert ("头晕" in summary_text) or ("恶心" in summary_text), summary_text
    finally:
        _cleanup(doctor_id)


def test_patient_chat_repeated_escalations_suppress_fourth_notification_ack_e2e():
    """Fourth non-urgent escalation in the window should switch to the suppression reply."""
    doctor_id = "inttest_chatrepeat_{0}".format(uuid.uuid4().hex[:8])
    _setup_doctor(doctor_id)

    try:
        reg = _register_patient(doctor_id, name="重复上报患者")
        patient_id = reg["patient_id"]
        token = reg["token"]

        replies: List[str] = []
        for idx in range(4):
            resp = _post_chat(token, "头痛比昨天严重了，吃止疼药也不管用，第{0}次".format(idx + 1))
            assert resp.status_code == 200, resp.text
            replies.append(resp.json()["reply"])

        assert "已通知医生" in replies[0], replies
        assert "医生将在查看时一并处理您的问题" in replies[-1], replies

        rows = _fetch_chat_rows(patient_id, doctor_id)
        assert len(rows) == 8, rows
        assert len(_inbound_rows(rows)) == 4, rows
        assert len(_outbound_rows(rows)) == 4, rows
    finally:
        _cleanup(doctor_id)


def test_patient_chat_urgent_bypasses_prior_nonurgent_suppression_e2e():
    """Urgent red flags should bypass the non-urgent suppression path."""
    doctor_id = "inttest_chaturgent_{0}".format(uuid.uuid4().hex[:8])
    _setup_doctor(doctor_id)

    try:
        reg = _register_patient(doctor_id, name="紧急消息患者")
        patient_id = reg["patient_id"]
        token = reg["token"]

        for idx in range(3):
            resp = _post_chat(token, "头痛比昨天严重了，吃止疼药也不管用，第{0}次".format(idx + 1))
            assert resp.status_code == 200, resp.text

        urgent = _post_chat(token, "胸口突然很痛，喘不上来气")
        assert urgent.status_code == 200, urgent.text

        body = urgent.json()
        assert body["triage_category"] == "urgent", body
        assert body["ai_handled"] is False, body
        assert ("立即就医" in body["reply"]) or ("120" in body["reply"]), body

        rows = _fetch_chat_rows(patient_id, doctor_id)
        inbound = _inbound_rows(rows)[-1]
        outbound = _outbound_rows(rows)[-1]
        assert inbound["triage_category"] == "urgent", rows
        assert outbound["triage_category"] == "urgent", rows
    finally:
        _cleanup(doctor_id)


def test_patient_chat_followup_question_uses_recent_message_context_e2e():
    """Second-turn vague follow-up should retain the prior symptom context."""
    doctor_id = "inttest_chatrecent_{0}".format(uuid.uuid4().hex[:8])
    _setup_doctor(doctor_id)

    try:
        reg = _register_patient(doctor_id, name="上下文患者")
        patient_id = reg["patient_id"]
        token = reg["token"]

        first = _post_chat(token, "昨天吃完新开的药以后一直头晕，还有点恶心")
        assert first.status_code == 200, first.text
        assert first.json()["triage_category"] != "informational", first.json()

        second = _post_chat(token, "现在还是这样，正常吗？")
        assert second.status_code == 200, second.text

        body = second.json()
        assert body["triage_category"] != "informational", body

        rows = _fetch_chat_rows(patient_id, doctor_id)
        assert len(rows) == 4, rows
        second_inbound = _inbound_rows(rows)[-1]
        summary = _parse_summary(second_inbound)
        summary_text = json.dumps(summary, ensure_ascii=False)

        assert ("头晕" in summary_text) or ("恶心" in summary_text) or ("药" in summary_text), (
            "The second-turn follow-up summary dropped the recent symptom context: {0}".format(summary_text)
        )
    finally:
        _cleanup(doctor_id)
