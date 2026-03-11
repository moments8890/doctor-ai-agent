"""多网关共享 DB 状态的端到端测试。

验证同一医生在文字网关与语音网关产生的记录写入同一患者时间线。

E2E test: one doctor flow across multiple gateways shares the same DB state.

This test starts from human-language inputs on:
- text gateway: `/api/records/chat`
- voice gateway: `/api/voice/chat`

It verifies both gateways write to the same patient timeline in DB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from db.crud import find_patient_by_name, get_records_for_patient
from routers.records import router as records_router
from routers.voice import router as voice_router
from services.ai.intent import Intent, IntentResult


def _build_records_dispatch(patient_name: str):
    """构建文字网关的模拟 dispatch 函数。"""
    async def _records_dispatch(text: str, history=None):
        if "创建" in text:
            return IntentResult(
                intent=Intent.create_patient,
                patient_name=patient_name,
                gender="男",
                age=57,
                chat_reply="已创建",
            )
        return IntentResult(
            intent=Intent.add_record,
            patient_name=patient_name,
            structured_fields={
                "chief_complaint": "胸痛2天",
                "history_of_present_illness": "活动后加重",
                "diagnosis": "疑似ACS",
                "treatment_plan": "完善心电图和肌钙蛋白",
            },
            chat_reply="已记录首诊病历",
        )
    return _records_dispatch


def _build_voice_dispatch(patient_name: str):
    """构建语音网关的模拟 dispatch 函数。"""
    async def _voice_dispatch(text: str, history=None):
        return IntentResult(
            intent=Intent.add_record,
            patient_name=patient_name,
            structured_fields={
                "chief_complaint": "今晨胸闷加重",
                "history_of_present_illness": "伴轻度气短",
                "diagnosis": "ACS待排",
                "treatment_plan": "继续观察并复查指标",
            },
            chat_reply="已补充语音病历",
        )
    return _voice_dispatch


async def _send_multi_gateway_requests(client, doctor_id: str, patient_name: str) -> None:
    """依次向文字网关和语音网关发送请求并断言响应。"""
    create_resp = await client.post(
        "/api/records/chat",
        json={
            "doctor_id": doctor_id,
            "text": f"请帮我创建，{patient_name}，男，57岁",
            "history": [],
        },
    )
    assert create_resp.status_code == 200
    assert "创建" in create_resp.json()["reply"]

    text_record_resp = await client.post(
        "/api/records/chat",
        json={
            "doctor_id": doctor_id,
            "text": f"{patient_name} 胸痛2天，活动后加重",
            "history": [],
        },
    )
    assert text_record_resp.status_code == 200
    assert text_record_resp.json().get("record") is not None

    voice_record_resp = await client.post(
        "/api/voice/chat",
        data={"doctor_id": doctor_id},
        files={"audio": ("voice.wav", b"fake-wave-bytes", "audio/wav")},
    )
    assert voice_record_resp.status_code == 200
    assert voice_record_resp.json().get("record") is not None


async def test_multi_gateway_human_language_e2e(session_factory):
    """多网关共享 DB 状态的端到端测试。"""
    app = FastAPI()
    app.include_router(records_router)
    app.include_router(voice_router)

    doctor_id = "inttest_multi_gateway_doc"
    patient_name = "跨网关患者甲"

    records_dispatch = _build_records_dispatch(patient_name)
    voice_dispatch = _build_voice_dispatch(patient_name)

    with patch("routers.records.AsyncSessionLocal", session_factory), \
         patch("routers.voice.AsyncSessionLocal", session_factory), \
         patch("routers.records.agent_dispatch", new=AsyncMock(side_effect=records_dispatch)), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(side_effect=voice_dispatch)), \
         patch("routers.voice.transcribe_audio", new=AsyncMock(return_value=f"{patient_name} 今天胸闷更重")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await _send_multi_gateway_requests(client, doctor_id, patient_name)

    async with session_factory() as db:
        patient = await find_patient_by_name(db, doctor_id, patient_name)
        assert patient is not None
        records = await get_records_for_patient(db, doctor_id, patient.id, limit=10)

    assert len(records) == 2
    complaints = [r.chief_complaint or "" for r in records]
    assert any("胸痛" in c for c in complaints)
    assert any("胸闷" in c for c in complaints)
