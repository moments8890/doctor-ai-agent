from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import httpx

from e2e.integration.conftest import DB_PATH, SERVER, chat

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "e2e" / "fixtures" / "data" / "realworld_doctor_agent_chatlogs_e2e_v2.json"


def test_realworld_v2_dataset_has_100_cases():
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert len(raw) == 100
    for case in raw:
        assert str(case.get("case_id", "")).startswith("REALWORLD-V2-")
        chatlog = case.get("chatlog", [])
        assert isinstance(chatlog, list) and len(chatlog) >= 4
        doctor_turns = [x for x in chatlog if str(x.get("speaker", "")).lower() == "doctor"]
        assert len(doctor_turns) >= 3
        exp = case.get("expectations", {})
        assert isinstance(exp, dict)
        assert exp.get("must_not_timeout") is True


def test_realworld_v2_table_coverage_e2e():
    doctor_id = "inttest_v2_tables_{0}".format(uuid.uuid4().hex[:8])

    r1 = chat("新患者张城，男，47岁。", doctor_id=doctor_id, server_url=SERVER)
    assert "reply" in r1

    r2 = chat("张城，胸痛2小时伴大汗，考虑STEMI，记录并保存。", doctor_id=doctor_id, server_url=SERVER)
    assert "reply" in r2

    r3 = chat("总结上下文：张城本次急性胸痛，按高危流程随访。", doctor_id=doctor_id, server_url=SERVER)
    assert "已保存医生上下文摘要" in str(r3.get("reply", ""))

    r4 = chat("为张城安排复诊 2026-03-20T14:00:00", doctor_id=doctor_id, server_url=SERVER)
    assert "任务编号" in str(r4.get("reply", ""))

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
    neuro_json = resp.json()
    assert int(neuro_json.get("db_id", 0)) > 0

    conn = sqlite3.connect(DB_PATH)
    try:
        counts = {}
        for table in [
            "doctors",
            "patients",
            "medical_records",
            "doctor_tasks",
            "doctor_contexts",
            "neuro_cases",
        ]:
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
