"""语音路由测试：验证语音对话 (voice_chat) 和问诊录音 (voice_consultation)
接口的错误处理、5-layer 工作流路由、共享处理器分发及草稿安全语义。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import routers.voice as voice
from db.models.medical_record import MedicalRecord
from utils.errors import InvalidMedicalRecordError
from services.ai.intent import Intent, IntentResult
from services.domain.intent_handlers._types import HandlerResult
from services.intent_workflow.models import (
    IntentDecision,
    EntityResolution,
    EntitySlot,
    BindingDecision,
    ActionPlan,
    GateResult,
    WorkflowResult,
)


DOCTOR = "voice_router_doc"


class _SessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Upload:
    def __init__(self, *, content_type: str, data: bytes = b"x", filename: str = "f.wav"):
        self.content_type = content_type
        self._data = data
        self.filename = filename

    async def read(self):
        return self._data


def _record() -> MedicalRecord:
    return MedicalRecord(content="胸痛 冠心病 随访", tags=["冠心病"])


def _workflow_result(
    intent: Intent = Intent.unknown,
    patient_name: str = None,
    chat_reply: str = None,
    gate_approved: bool = True,
    gate_reason: str = None,
    gate_message: str = None,
    is_emergency: bool = False,
    structured_fields: dict = None,
) -> WorkflowResult:
    """Build a minimal WorkflowResult for testing."""
    return WorkflowResult(
        decision=IntentDecision(
            intent=intent, source="fast_route",
            chat_reply=chat_reply, structured_fields=structured_fields,
        ),
        entities=EntityResolution(
            patient_name=EntitySlot(value=patient_name, source="llm") if patient_name else None,
            is_emergency=is_emergency,
        ),
        binding=BindingDecision(status="bound" if patient_name else "no_name"),
        plan=ActionPlan(),
        gate=GateResult(
            approved=gate_approved, reason=gate_reason,
            clarification_message=gate_message,
        ),
    )


def _hr(reply: str, **kwargs) -> HandlerResult:
    return HandlerResult(reply=reply, **kwargs)


# --------------------------------------------------------------------------
# voice_chat — error handling (pre-workflow)
# --------------------------------------------------------------------------


async def test_voice_chat_unsupported_type():
    upload = _Upload(content_type="audio/aac")
    with pytest.raises(HTTPException) as exc:
        await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert exc.value.status_code == 422


async def test_voice_chat_transcription_error():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(side_effect=RuntimeError("model error"))):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert exc.value.status_code == 500


async def test_voice_chat_empty_transcript():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="  ")):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert exc.value.status_code == 422


async def test_voice_chat_malformed_history():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history="not json")
    assert exc.value.status_code == 422


async def test_voice_chat_history_not_a_list():
    """Valid JSON but not a list raises 422."""
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history='{"key": "val"}')
    assert exc.value.status_code == 422


# --------------------------------------------------------------------------
# voice_chat — workflow error handling
# --------------------------------------------------------------------------


async def test_voice_chat_workflow_rate_limit():
    """Workflow raising rate-limit error maps to 429."""
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(
             side_effect=RuntimeError("429 rate_limit")
         )):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert exc.value.status_code == 429
    assert exc.value.detail == "rate_limit_exceeded"


async def test_voice_chat_workflow_error():
    """Workflow raising non-rate-limit error maps to 503."""
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(
             side_effect=RuntimeError("service down")
         )):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert exc.value.status_code == 503


# --------------------------------------------------------------------------
# voice_chat — gate rejection
# --------------------------------------------------------------------------


async def test_voice_chat_gate_rejected():
    """Gate rejection (not no_patient_name) returns clarification message."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(
        intent=Intent.add_record,
        gate_approved=False,
        gate_reason="unsafe_operation",
        gate_message="请先确认操作。",
    )
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="做手术")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.reply == "请先确认操作。"
    assert resp.record is None


async def test_voice_chat_gate_no_patient_name_passes_through():
    """Gate rejection with no_patient_name lets shared handler resolve patient."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(
        intent=Intent.add_record,
        gate_approved=False,
        gate_reason="no_patient_name",
    )
    hr = _hr("请问这位患者叫什么名字？")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="胸痛发作")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_add_record", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "叫什么名字" in resp.reply


# --------------------------------------------------------------------------
# voice_chat — intent dispatch through shared handlers
# --------------------------------------------------------------------------


async def test_voice_chat_unknown_intent():
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.unknown, chat_reply="您好！")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="你好")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.transcript == "你好"
    assert "您好" in resp.reply
    assert resp.record is None


async def test_voice_chat_create_patient_via_shared_handler():
    """create_patient dispatches to shared handler."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.create_patient, patient_name="赵六")
    hr = _hr("✅ 已为患者【赵六】创建（女、30岁）。")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="创建赵六")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_create_patient", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "赵六" in resp.reply
    assert resp.transcript == "创建赵六"


async def test_voice_chat_create_patient_no_name_asks():
    """create_patient with no name returns ask-for-name reply."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.create_patient)
    hr = _hr("好的，请告诉我患者的姓名。")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="创建")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_create_patient", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "姓名" in resp.reply
    assert resp.record is None


async def test_voice_chat_add_record_creates_pending_draft():
    """Normal add_record creates a pending draft, NOT a direct save."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.add_record, patient_name="李明")
    hr = _hr(
        reply="📋 已为【李明】生成病历草稿，请确认后保存。",
        record=_record(),
        pending_id="draft-abc",
        pending_patient_name="李明",
        pending_expires_at="2026-03-12T10:00:00",
    )
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="李明胸痛")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_add_record", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.pending_id == "draft-abc"
    assert resp.pending_patient_name == "李明"
    assert resp.record is not None
    assert "草稿" in resp.reply


async def test_voice_chat_add_record_emergency_saves_directly():
    """Emergency add_record saves directly (no pending_id)."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.add_record, patient_name="急诊王", is_emergency=True)
    hr = _hr(reply="🚨 紧急病历已为【急诊王】直接保存。", record=_record())
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="急诊王心梗")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_add_record", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.pending_id is None
    assert resp.record is not None
    assert "紧急" in resp.reply


async def test_voice_chat_add_record_no_patient_name_asks():
    """add_record with no patient name asks for name via shared handler."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(
        intent=Intent.add_record,
        gate_approved=False, gate_reason="no_patient_name",
    )
    hr = _hr("请问这位患者叫什么名字？")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="胸痛")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_add_record", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "叫什么名字" in resp.reply


async def test_voice_chat_add_record_switch_notification():
    """Patient switch notification is propagated to VoiceChatResponse."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.add_record, patient_name="新患者")
    hr = _hr(
        reply="📋 已为【新患者】生成病历草稿。",
        record=_record(), pending_id="def456",
        switch_notification="🔄 已从【旧患者】切换到【新患者】",
    )
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="新患者胸痛")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_add_record", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.switch_notification == "🔄 已从【旧患者】切换到【新患者】"


async def test_voice_chat_add_record_structuring_error():
    """Structuring failure returns error reply via shared handler."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.add_record, patient_name="王三")
    hr = _hr("病历生成失败，请稍后重试。")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="王三胸闷")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_add_record", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "病历生成失败" in resp.reply


async def test_voice_chat_query_records_via_shared_handler():
    """query_records dispatches to shared handler."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.query_records, patient_name="张三")
    hr = _hr("📂 患者【张三】最近 3 条记录：\n1. 胸痛")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查张三病历")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_query_records", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "张三" in resp.reply


async def test_voice_chat_list_patients_via_shared_handler():
    """list_patients dispatches to shared handler."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.list_patients)
    hr = _hr("👥 共 2 位患者：\n1. 张三\n2. 李四")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="所有患者")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_list_patients", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "共 2 位患者" in resp.reply


async def test_voice_chat_help_intent():
    """help intent returns help text directly."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.help)
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="帮助")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "建档" in resp.reply
    assert "病历" in resp.reply


# --------------------------------------------------------------------------
# voice_chat — followup name override
# --------------------------------------------------------------------------


async def test_voice_chat_followup_name_forces_add_record():
    """When previous turn asked for name and transcript is name-only,
    intent is overridden to add_record regardless of workflow classification."""
    upload = _Upload(content_type="audio/wav")
    history_json = json.dumps([{"role": "assistant", "content": "请问这位患者叫什么名字？"}])
    wf = _workflow_result(intent=Intent.unknown, chat_reply="ok")
    hr = _hr(reply="📋 已为【李四】生成病历草稿。", record=_record(), pending_id="draft-fu")
    add_record_mock = AsyncMock(return_value=hr)
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="李四")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_add_record", new=add_record_mock):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=history_json)
    add_record_mock.assert_called_once()
    assert resp.pending_id == "draft-fu"
    _, kwargs = add_record_mock.call_args
    assert kwargs.get("followup_name") == "李四"


async def test_voice_chat_followup_name_already_add_record():
    """When followup_name is set and workflow classified as add_record, handler still called."""
    upload = _Upload(content_type="audio/wav")
    history_json = json.dumps([{"role": "assistant", "content": "请问这位患者叫什么名字？"}])
    wf = _workflow_result(intent=Intent.add_record, patient_name="李四")
    hr = _hr(reply="📋 已为【李四】生成病历草稿。", record=_record(), pending_id="draft-ok")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="李四")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_add_record", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=history_json)
    assert resp.pending_id == "draft-ok"


# --------------------------------------------------------------------------
# voice_chat — history passed to workflow
# --------------------------------------------------------------------------


async def test_voice_chat_history_json_passed_to_workflow():
    upload = _Upload(content_type="audio/wav")
    history_list = [{"role": "user", "content": "hello"}]
    history_json = json.dumps(history_list)
    wf = _workflow_result(intent=Intent.unknown, chat_reply="ok")
    workflow_mock = AsyncMock(return_value=wf)
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=workflow_mock):
        await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=history_json)
    workflow_mock.assert_called_once()
    call_args = workflow_mock.call_args
    assert call_args[0][2] == history_list


# --------------------------------------------------------------------------
# voice_chat — task management intents
# --------------------------------------------------------------------------


async def test_voice_chat_postpone_task():
    """postpone_task dispatches to shared handler."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.postpone_task)
    hr = _hr("✅ 已将任务推迟至下周。")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="推迟任务")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_postpone_task", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "推迟" in resp.reply


async def test_voice_chat_cancel_task():
    """cancel_task dispatches to shared handler."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.cancel_task)
    hr = _hr("✅ 已取消该任务。")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="取消任务")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_cancel_task", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "取消" in resp.reply


async def test_voice_chat_schedule_follow_up():
    """schedule_follow_up dispatches to shared handler."""
    upload = _Upload(content_type="audio/wav")
    wf = _workflow_result(intent=Intent.schedule_follow_up)
    hr = _hr("✅ 已为患者创建随访任务。")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="安排随访")), \
         patch("routers.voice.hydrate_session_state", new=AsyncMock()), \
         patch("services.intent_workflow.run", new=AsyncMock(return_value=wf)), \
         patch("routers.voice.shared_handle_schedule_follow_up", new=AsyncMock(return_value=hr)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "随访" in resp.reply


# --------------------------------------------------------------------------
# voice_consultation tests (unchanged — consultation still saves directly)
# --------------------------------------------------------------------------


async def test_consultation_unsupported_type():
    upload = _Upload(content_type="audio/aac")
    with pytest.raises(HTTPException) as exc:
        await voice.voice_consultation(
            audio=upload, doctor_id=DOCTOR, patient_name=None, save=False
        )
    assert exc.value.status_code == 422


async def test_consultation_transcription_error():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(side_effect=RuntimeError("fail"))):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_consultation(
                audio=upload, doctor_id=DOCTOR, patient_name=None, save=False
            )
    assert exc.value.status_code == 500


async def test_consultation_structuring_error():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="医患对话")), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("llm down"))):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_consultation(
                audio=upload, doctor_id=DOCTOR, patient_name=None, save=False
            )
    assert exc.value.status_code == 500


async def test_consultation_no_save():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="医患对话")), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())):
        resp = await voice.voice_consultation(
            audio=upload, doctor_id=DOCTOR, patient_name=None, save=False
        )
    assert "胸痛" in resp.record.content
    assert resp.patient_id is None


async def test_consultation_save_existing_patient():
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    patient = SimpleNamespace(id=42, name="张三")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="医患对话")), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("db.engine.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("db.crud.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("db.crud.save_record", new=AsyncMock()):
        resp = await voice.voice_consultation(
            audio=upload, doctor_id=DOCTOR, patient_name="张三", save=True
        )
    assert resp.patient_id == 42


async def test_consultation_save_creates_new_patient():
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    new_patient = SimpleNamespace(id=99, name="王五")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="医患对话")), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("db.engine.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("db.crud.find_patient_by_name", new=AsyncMock(return_value=None)), \
         patch("db.crud.create_patient", new=AsyncMock(return_value=new_patient)) as create_mock, \
         patch("db.crud.save_record", new=AsyncMock()):
        resp = await voice.voice_consultation(
            audio=upload, doctor_id=DOCTOR, patient_name="王五", save=True
        )
    assert resp.patient_id == 99
    create_mock.assert_called_once()


async def test_consultation_save_no_patient_name():
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    save_mock = AsyncMock()
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="医患对话")), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("db.engine.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("db.crud.save_record", new=save_mock):
        resp = await voice.voice_consultation(
            audio=upload, doctor_id=DOCTOR, patient_name=None, save=True
        )
    assert resp.patient_id is None
    save_mock.assert_called_once()


async def test_consultation_transcribe_consultation_mode():
    upload = _Upload(content_type="audio/wav")
    transcribe_mock = AsyncMock(return_value="医患对话")
    with patch("routers.voice.transcribe_audio", new=transcribe_mock), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())):
        await voice.voice_consultation(
            audio=upload, doctor_id=DOCTOR, patient_name=None, save=False
        )
    transcribe_mock.assert_called_once()
    _, kwargs = transcribe_mock.call_args
    assert kwargs.get("consultation_mode") is True


async def test_consultation_structure_consultation_mode():
    upload = _Upload(content_type="audio/wav")
    structure_mock = AsyncMock(return_value=_record())
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="医患对话")), \
         patch("routers.voice.structure_medical_record", new=structure_mock):
        await voice.voice_consultation(
            audio=upload, doctor_id=DOCTOR, patient_name=None, save=False
        )
    structure_mock.assert_called_once()
    _, kwargs = structure_mock.call_args
    assert kwargs.get("consultation_mode") is True


async def test_consultation_empty_transcript():
    """voice_consultation raises 422 when transcript is blank."""
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="   ")):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_consultation(
                audio=upload, doctor_id=DOCTOR, patient_name=None, save=False
            )
    assert exc.value.status_code == 422
