"""会话持久化测试：验证会话状态写入数据库、重启后水合恢复及历史对话轮次的持久化行为。"""

import asyncio
from unittest.mock import patch

from db.crud import create_patient
from services import session as sess_mod


DOCTOR = "persist_doc"


async def test_persist_and_hydrate_session_state(session_factory):
    async with session_factory() as db:
        patient = await create_patient(db, DOCTOR, "张三", "男", 30)

    with patch("services.session.AsyncSessionLocal", session_factory):
        sess_mod.set_current_patient(DOCTOR, patient.id, patient.name, persist=False)
        sess_mod.set_pending_create(DOCTOR, "李四", persist=False)
        await sess_mod.persist_session_state(DOCTOR)

        # Simulate a redeploy/process restart by clearing in-memory cache.
        sess_mod._sessions.clear()
        sess_mod._loaded_from_db.clear()

        restored = await sess_mod.hydrate_session_state(DOCTOR)

    assert restored.current_patient_id == patient.id
    assert restored.current_patient_name == "张三"
    assert restored.pending_create_name == "李四"


async def test_hydrate_clears_stale_patient_name_if_patient_missing(session_factory):
    with patch("services.session.AsyncSessionLocal", session_factory):
        # Write a state that points to a non-existent patient id.
        sess_mod.set_current_patient(DOCTOR, 9999, "不存在", persist=False)
        sess_mod.clear_pending_create(DOCTOR, persist=False)
        await sess_mod.persist_session_state(DOCTOR)

        sess_mod._sessions.clear()
        sess_mod._loaded_from_db.clear()
        restored = await sess_mod.hydrate_session_state(DOCTOR)

    assert restored.current_patient_id == 9999
    assert restored.current_patient_name is None


async def test_hydrate_restores_recent_conversation_turns(session_factory):
    with patch("services.session.AsyncSessionLocal", session_factory):
        sess_mod.push_turn(DOCTOR, "患者胸痛2小时", "已记录，建议心电图")
        # wait for async persistence task scheduled by push_turn
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        sess_mod._sessions.clear()
        sess_mod._loaded_from_db.clear()

        restored = await sess_mod.hydrate_session_state(DOCTOR)

    assert len(restored.conversation_history) >= 2
    assert restored.conversation_history[-2]["role"] == "user"
    assert restored.conversation_history[-2]["content"] == "患者胸痛2小时"
    assert restored.conversation_history[-1]["role"] == "assistant"
    assert "已记录" in restored.conversation_history[-1]["content"]
