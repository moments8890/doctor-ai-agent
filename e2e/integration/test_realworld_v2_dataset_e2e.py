"""真实世界 V2 数据集端到端测试。

验证 1020 条案例数据集的结构完整性，并通过端到端流程覆盖所有关键 DB 表。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import httpx

from e2e.integration.conftest import DB_PATH, SERVER, chat

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v2.json"


def test_realworld_v2_dataset_has_1020_cases():
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert len(raw) == 1020

    correction_cases = [c for c in raw if "CORRECTION" in str(c.get("case_id", ""))]
    assert len(correction_cases) == 20, (
        f"Expected 20 correction cases, got {len(correction_cases)}"
    )

    for case in raw:
        cid = str(case.get("case_id", ""))
        assert cid.startswith("REALWORLD-V2-"), f"Bad case_id prefix: {cid}"
        chatlog = case.get("chatlog", [])
        assert isinstance(chatlog, list) and len(chatlog) >= 3, (
            f"{cid}: chatlog must have ≥3 turns, got {len(chatlog)}"
        )
        doctor_turns = [x for x in chatlog if str(x.get("speaker", "")).lower() == "doctor"]
        assert len(doctor_turns) >= 3, (
            f"{cid}: needs ≥3 doctor turns, got {len(doctor_turns)}"
        )
        exp = case.get("expectations", {})
        assert isinstance(exp, dict)
        assert exp.get("must_not_timeout") is True, f"{cid}: missing must_not_timeout"

    # Correction cases must declare correction_type
    for case in correction_cases:
        exp = case.get("expectations", {})
        assert "correction_type" in exp, (
            f"{case['case_id']}: correction cases must have expectations.correction_type"
        )


def _send_e2e_chat_turns(doctor_id: str) -> None:
    """发送建档、病历、上下文、随访任务四轮对话，并断言响应。"""
    r1 = chat("新患者张城，男，47岁。", doctor_id=doctor_id, server_url=SERVER)
    assert "reply" in r1

    r2 = chat("张城，胸痛2小时伴大汗，考虑STEMI，记录并保存。", doctor_id=doctor_id, server_url=SERVER)
    assert "reply" in r2

    r3 = chat("总结上下文：张城本次急性胸痛，按高危流程随访。", doctor_id=doctor_id, server_url=SERVER)
    assert "已保存医生上下文摘要" in str(r3.get("reply", ""))

    r4 = chat("为张城安排复诊 2026-03-20T14:00:00", doctor_id=doctor_id, server_url=SERVER)
    assert "任务编号" in str(r4.get("reply", ""))


def _send_neuro_case(doctor_id: str) -> None:
    """通过神经病例接口提交卒中数据并断言返回 db_id。"""
    neuro_payload = {
        "doctor_id": doctor_id,
        "text": "张城，男，47岁，突发言语不清2小时，右侧肢体无力，NIHSS 8分，考虑急性缺血性卒中。",
    }
    resp = httpx.post(
        "{0}/api/neuro/from-text".format(SERVER),
        json=neuro_payload,
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0),
    )
    resp.raise_for_status()
    assert int(resp.json().get("db_id", 0)) > 0


def _assert_db_table_counts(doctor_id: str) -> None:
    """查询 DB 各表计数并断言全部 >= 1。"""
    conn = sqlite3.connect(DB_PATH)
    try:
        counts = {}
        for table in ["doctors", "patients", "medical_records", "doctor_tasks", "doctor_contexts", "neuro_cases"]:
            row = conn.execute(
                "SELECT COUNT(1) FROM {0} WHERE doctor_id=?".format(table),
                (doctor_id,),
            ).fetchone()
            counts[table] = int(row[0] if row else 0)
        prompts = conn.execute("SELECT COUNT(1) FROM system_prompts").fetchone()
        counts["system_prompts"] = int(prompts[0] if prompts else 0)
    finally:
        conn.close()

    assert counts["patients"] >= 1
    assert counts["medical_records"] >= 1
    assert counts["doctor_tasks"] >= 1
    assert counts["doctor_contexts"] >= 1
    assert counts["neuro_cases"] >= 1
    assert counts["system_prompts"] >= 1


def test_realworld_v2_table_coverage_e2e():
    """通过完整端到端流程覆盖所有关键 DB 表。"""
    doctor_id = "inttest_v2_tables_{0}".format(uuid.uuid4().hex[:8])
    _send_e2e_chat_turns(doctor_id)
    _send_neuro_case(doctor_id)
    _assert_db_table_counts(doctor_id)
