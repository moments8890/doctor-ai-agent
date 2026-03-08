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


def _intent(intent: Intent, **kwargs) -> IntentResult:
    return IntentResult(intent=intent, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# voice_chat tests
# ─────────────────────────────────────────────────────────────────────────────


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


async def test_voice_chat_dispatch_rate_limit():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(side_effect=RuntimeError("429 rate_limit"))):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert exc.value.status_code == 429
    assert exc.value.detail == "rate_limit_exceeded"


async def test_voice_chat_dispatch_error():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(side_effect=RuntimeError("service down"))):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert exc.value.status_code == 503


async def test_voice_chat_unknown_intent():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="你好")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.unknown, chat_reply="您好！")
         )):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.transcript == "你好"
    assert "您好" in resp.reply
    assert resp.record is None


async def test_voice_chat_add_record_with_structured_fields():
    upload = _Upload(content_type="audio/wav")
    fields = {"content": "胸痛 冠心病", "tags": ["冠心病"]}
    fake_db = object()
    patient = SimpleNamespace(id=7, name="李明")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="李明胸痛")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.add_record, patient_name="李明", structured_fields=fields)
         )), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("routers.voice.save_record", new=AsyncMock()):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.transcript == "李明胸痛"
    assert resp.record is not None
    assert "胸痛" in resp.record.content


async def test_voice_chat_history_json_parsed():
    upload = _Upload(content_type="audio/wav")
    history_list = [{"role": "user", "content": "hello"}]
    history_json = json.dumps(history_list)
    dispatch_mock = AsyncMock(return_value=_intent(Intent.unknown, chat_reply="ok"))
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")), \
         patch("routers.voice.agent_dispatch", new=dispatch_mock):
        await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=history_json)
    dispatch_mock.assert_called_once()
    call_kwargs = dispatch_mock.call_args
    assert call_kwargs[1]["history"] == history_list


async def test_voice_chat_malformed_history():
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history="not json")
    assert exc.value.status_code == 422


async def test_voice_chat_create_patient_with_name():
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    patient = SimpleNamespace(id=5, name="赵六")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="建档赵六")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.create_patient, patient_name="赵六", gender="女", age=30)
         )), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.db_create_patient", new=AsyncMock(return_value=patient)):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "赵六" in resp.reply
    assert resp.transcript == "建档赵六"


async def test_voice_chat_create_patient_invalid_name():
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="建档异常姓名")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.create_patient, patient_name="异常姓名", gender="女", age=30)
         )), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.db_create_patient", new=AsyncMock(side_effect=InvalidMedicalRecordError("invalid"))):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "姓名格式无效" in resp.reply


async def test_voice_chat_add_record_structuring_fallback():
    """add_record without structured_fields falls back to structure_medical_record."""
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    patient = SimpleNamespace(id=3, name="陈七")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="陈七胸闷")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.add_record, patient_name="陈七")
         )), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("routers.voice.save_record", new=AsyncMock()):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.record is not None
    assert "陈七" in resp.reply


# ─────────────────────────────────────────────────────────────────────────────
# voice_consultation tests
# ─────────────────────────────────────────────────────────────────────────────


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
    save_mock = AsyncMock()
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="医患对话")), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("routers.voice.save_record", new=save_mock):
        resp = await voice.voice_consultation(
            audio=upload, doctor_id=DOCTOR, patient_name=None, save=False
        )
    assert "胸痛" in resp.record.content
    assert resp.patient_id is None
    save_mock.assert_not_called()


async def test_consultation_save_existing_patient():
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    patient = SimpleNamespace(id=42, name="张三")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="医患对话")), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("routers.voice.save_record", new=AsyncMock()):
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
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.find_patient_by_name", new=AsyncMock(return_value=None)), \
         patch("routers.voice.db_create_patient", new=AsyncMock(return_value=new_patient)) as create_mock, \
         patch("routers.voice.save_record", new=AsyncMock()):
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
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.save_record", new=save_mock):
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


# ─────────────────────────────────────────────────────────────────────────────
# Additional voice_chat branch coverage
# ─────────────────────────────────────────────────────────────────────────────


async def test_voice_chat_history_not_a_list():
    """Valid JSON but not a list raises 422."""
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="查患者")):
        with pytest.raises(HTTPException) as exc:
            await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history='{"key": "val"}')
    assert exc.value.status_code == 422


async def test_voice_chat_followup_name_two_turn():
    """When previous assistant message asked for name and transcript is name-only,
    intent is forced to add_record."""
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    patient = SimpleNamespace(id=8, name="李四")
    history_json = json.dumps([{"role": "assistant", "content": "请问这位患者叫什么名字？"}])
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="李四")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.unknown, chat_reply="ok")
         )), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("routers.voice.save_record", new=AsyncMock()):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=history_json)
    assert resp.record is not None


async def test_voice_chat_create_patient_no_name_asks():
    """create_patient with no name returns ask-for-name reply."""
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="建档")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.create_patient, patient_name=None)
         )):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "姓名" in resp.reply
    assert resp.record is None


async def test_voice_chat_add_record_no_name_asks():
    """add_record with invalid/missing patient_name returns ask-for-name reply."""
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="胸痛")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.add_record, patient_name=None)
         )):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "叫什么名字" in resp.reply


async def test_voice_chat_structured_fields_with_content():
    """structured_fields with content field creates a valid record."""
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    patient = SimpleNamespace(id=2, name="王二")
    fields = {"content": "冠心病随访", "tags": ["冠心病"]}
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="王二冠心病")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.add_record, patient_name="王二", structured_fields=fields)
         )), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.find_patient_by_name", new=AsyncMock(return_value=patient)), \
         patch("routers.voice.save_record", new=AsyncMock()):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert resp.record is not None
    assert "冠心病" in resp.record.content


async def test_voice_chat_add_record_structuring_error():
    """Structuring LLM failure in fallback path returns error reply (not 500)."""
    upload = _Upload(content_type="audio/wav")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="王三胸闷")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.add_record, patient_name="王三")
         )), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("llm err"))):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "病历生成失败" in resp.reply


async def test_voice_chat_add_record_new_patient_created():
    """add_record where patient doesn't exist triggers db_create_patient."""
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    new_patient = SimpleNamespace(id=55, name="新患者")
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="新患者胸痛")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.add_record, patient_name="新患者")
         )), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.find_patient_by_name", new=AsyncMock(return_value=None)), \
         patch("routers.voice.db_create_patient", new=AsyncMock(return_value=new_patient)) as create_mock, \
         patch("routers.voice.save_record", new=AsyncMock()):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    create_mock.assert_called_once()
    assert "新建档并" in resp.reply


async def test_voice_chat_add_record_new_patient_invalid_name():
    upload = _Upload(content_type="audio/wav")
    fake_db = object()
    with patch("routers.voice.transcribe_audio", new=AsyncMock(return_value="新患者胸痛")), \
         patch("routers.voice.agent_dispatch", new=AsyncMock(
             return_value=_intent(Intent.add_record, patient_name="新患者")
         )), \
         patch("routers.voice.structure_medical_record", new=AsyncMock(return_value=_record())), \
         patch("routers.voice.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), \
         patch("routers.voice.find_patient_by_name", new=AsyncMock(return_value=None)), \
         patch("routers.voice.db_create_patient", new=AsyncMock(side_effect=InvalidMedicalRecordError("invalid"))):
        resp = await voice.voice_chat(audio=upload, doctor_id=DOCTOR, history=None)
    assert "姓名格式无效" in resp.reply
