from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import routers.records as records
from models.medical_record import MedicalRecord
from services.intent import Intent, IntentResult


DOCTOR = "records_router_doc"


class _SessionCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Upload:
    def __init__(self, *, content_type: str, data: bytes = b"x", filename: str = "f.bin"):
        self.content_type = content_type
        self._data = data
        self.filename = filename

    async def read(self):
        return self._data


def _record():
    return MedicalRecord(chief_complaint="胸痛", diagnosis="冠心病", treatment_plan="随访")


def _intent(intent: Intent, **kwargs) -> IntentResult:
    return IntentResult(intent=intent, **kwargs)


def test_helper_name_validation_and_parsing():
    assert records._is_valid_patient_name("张三")
    assert not records._is_valid_patient_name("  ")
    assert not records._is_valid_patient_name("这位患者叫什么名字")
    assert not records._is_valid_patient_name("张" * 25)

    history = [{"role": "assistant", "content": "请问这位患者叫什么名字？"}]
    assert records._assistant_asked_for_name(history) is True
    assert records._assistant_asked_for_name([{"role": "user", "content": "x"}]) is False
    assert records._name_only_text("陈明") == "陈明"
    assert records._name_only_text("陈明，胸痛") is None


async def test_chat_empty_text_raises_422():
    with pytest.raises(HTTPException) as exc:
        await records.chat(records.ChatInput(text="   "))
    assert exc.value.status_code == 422


async def test_chat_dispatch_errors_map_to_429_and_503():
    with patch("routers.records.agent_dispatch", new=AsyncMock(side_effect=RuntimeError("429 rate_limit"))):
        with pytest.raises(HTTPException) as exc:
            await records.chat(records.ChatInput(text="x", doctor_id=DOCTOR))
    assert exc.value.status_code == 429

    with patch("routers.records.agent_dispatch", new=AsyncMock(side_effect=RuntimeError("service down"))):
        with pytest.raises(HTTPException) as exc2:
            await records.chat(records.ChatInput(text="x", doctor_id=DOCTOR))
    assert exc2.value.status_code == 503


async def test_chat_create_patient_no_name_and_success():
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.create_patient, patient_name=None)),
    ):
        resp = await records.chat(records.ChatInput(text="建档", doctor_id=DOCTOR))
    assert "姓名" in resp.reply

    fake_db = object()
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.create_patient, patient_name="李明", gender="男", age=40)),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.db_create_patient",
        new=AsyncMock(return_value=SimpleNamespace(id=1, name="李明")),
    ):
        resp2 = await records.chat(records.ChatInput(text="建档李明", doctor_id=DOCTOR))
    assert "建档" in resp2.reply
    assert "李明" in resp2.reply


async def test_chat_add_record_invalid_name_and_structuring_error():
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.add_record, patient_name=None)),
    ):
        resp = await records.chat(records.ChatInput(text="胸痛", doctor_id=DOCTOR))
    assert "叫什么名字" in resp.reply

    fake_db = object()
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.add_record, patient_name="张三")),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.structure_medical_record",
        new=AsyncMock(side_effect=RuntimeError("llm down")),
    ):
        resp2 = await records.chat(records.ChatInput(text="张三胸痛", doctor_id=DOCTOR))
    assert "病历生成失败" in resp2.reply


async def test_chat_query_records_branches():
    fake_db = object()
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name="张三")),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patient_by_name",
        new=AsyncMock(return_value=None),
    ):
        resp = await records.chat(records.ChatInput(text="查张三", doctor_id=DOCTOR))
    assert "未找到患者" in resp.reply

    patient = SimpleNamespace(id=11, name="张三")
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name="张三")),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patient_by_name",
        new=AsyncMock(return_value=patient),
    ), patch(
        "routers.records.get_records_for_patient",
        new=AsyncMock(return_value=[]),
    ):
        resp2 = await records.chat(records.ChatInput(text="查张三", doctor_id=DOCTOR))
    assert "暂无历史记录" in resp2.reply

    records_list = [
        SimpleNamespace(chief_complaint="胸痛", diagnosis="冠心病", created_at=datetime(2026, 3, 2))
    ]
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name="张三")),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patient_by_name",
        new=AsyncMock(return_value=patient),
    ), patch(
        "routers.records.get_records_for_patient",
        new=AsyncMock(return_value=records_list),
    ):
        resp3 = await records.chat(records.ChatInput(text="查张三", doctor_id=DOCTOR))
    assert "最近 1 条记录" in resp3.reply

    all_records = [SimpleNamespace(patient=None, chief_complaint=None, diagnosis=None, created_at=None)]
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name=None)),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.get_all_records_for_doctor",
        new=AsyncMock(return_value=[]),
    ):
        resp4 = await records.chat(records.ChatInput(text="查病历", doctor_id=DOCTOR))
    assert "暂无任何病历记录" in resp4.reply

    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name=None)),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.get_all_records_for_doctor",
        new=AsyncMock(return_value=all_records),
    ):
        resp5 = await records.chat(records.ChatInput(text="查病历", doctor_id=DOCTOR))
    assert "最近 1 条记录" in resp5.reply


async def test_chat_list_patients_and_unknown_reply():
    fake_db = object()
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.list_patients)),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.get_all_patients",
        new=AsyncMock(return_value=[]),
    ):
        resp = await records.chat(records.ChatInput(text="所有患者", doctor_id=DOCTOR))
    assert "暂无患者记录" in resp.reply

    patients = [SimpleNamespace(name="张三", gender="男", year_of_birth=1980)]
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.list_patients)),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.get_all_patients",
        new=AsyncMock(return_value=patients),
    ):
        resp2 = await records.chat(records.ChatInput(text="所有患者", doctor_id=DOCTOR))
    assert "共 1 位患者" in resp2.reply
    assert "张三" in resp2.reply

    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.unknown, chat_reply="你好医生")),
    ):
        resp3 = await records.chat(records.ChatInput(text="hi", doctor_id=DOCTOR))
    assert resp3.reply == "你好医生"

    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.unknown, chat_reply=None)),
    ):
        resp4 = await records.chat(records.ChatInput(text="hi", doctor_id=DOCTOR))
    assert "您好" in resp4.reply


async def test_from_text_image_audio_endpoints():
    with pytest.raises(HTTPException) as exc:
        await records.create_record_from_text(records.TextInput(text=" "))
    assert exc.value.status_code == 422

    with patch("routers.records.structure_medical_record", new=AsyncMock(return_value=_record())):
        rec = await records.create_record_from_text(records.TextInput(text="胸痛"))
    assert rec.chief_complaint == "胸痛"

    with patch("routers.records.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(HTTPException) as exc2:
            await records.create_record_from_text(records.TextInput(text="胸痛"))
    assert exc2.value.status_code == 500

    with pytest.raises(HTTPException) as exc3:
        await records.create_record_from_image(_Upload(content_type="image/tiff"))
    assert exc3.value.status_code == 422

    with patch("routers.records.extract_text_from_image", new=AsyncMock(return_value="识别文本")), \
         patch("routers.records.structure_medical_record", new=AsyncMock(return_value=_record())):
        rec2 = await records.create_record_from_image(_Upload(content_type="image/png", data=b"img"))
    assert rec2.chief_complaint == "胸痛"

    with patch("routers.records.extract_text_from_image", new=AsyncMock(side_effect=RuntimeError("ocr fail"))):
        with pytest.raises(HTTPException) as exc4:
            await records.create_record_from_image(_Upload(content_type="image/png", data=b"img"))
    assert exc4.value.status_code == 500

    with pytest.raises(HTTPException) as exc5:
        await records.create_record_from_audio(_Upload(content_type="audio/aac"))
    assert exc5.value.status_code == 422

    with patch("routers.records.transcribe_audio", new=AsyncMock(return_value="转写文本")), \
         patch("routers.records.structure_medical_record", new=AsyncMock(return_value=_record())):
        rec3 = await records.create_record_from_audio(_Upload(content_type="audio/wav", data=b"wav", filename="a.wav"))
    assert rec3.chief_complaint == "胸痛"

    with patch("routers.records.transcribe_audio", new=AsyncMock(side_effect=RuntimeError("asr fail"))):
        with pytest.raises(HTTPException) as exc6:
            await records.create_record_from_audio(_Upload(content_type="audio/wav", data=b"wav", filename="a.wav"))
    assert exc6.value.status_code == 500


# ---------------------------------------------------------------------------
# Approval-mode branch tests
# ---------------------------------------------------------------------------


async def test_chat_add_record_approval_mode_enabled_returns_pending_id(monkeypatch):
    """With APPROVAL_MODE_ENABLED=true, add_record should NOT call save_record
    and should return pending_approval_id."""
    monkeypatch.setenv("APPROVAL_MODE_ENABLED", "true")

    fake_db = object()
    fake_approval = SimpleNamespace(id=7)

    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(
            Intent.add_record,
            patient_name="张三",
            structured_fields={"chief_complaint": "胸痛"},
        )),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patient_by_name",
        new=AsyncMock(return_value=None),
    ), patch(
        "routers.records.create_approval_item",
        new=AsyncMock(return_value=fake_approval),
    ), patch(
        "routers.records.save_record",
        new=AsyncMock(),
    ) as mock_save:
        resp = await records.chat(records.ChatInput(text="张三胸痛", doctor_id=DOCTOR))

    assert resp.pending_approval_id == 7
    mock_save.assert_not_called()


async def test_chat_add_record_approval_mode_disabled_uses_direct_write(monkeypatch):
    """With APPROVAL_MODE_ENABLED=false (default), add_record calls save_record
    and returns no pending_approval_id."""
    monkeypatch.setenv("APPROVAL_MODE_ENABLED", "false")

    fake_db = object()
    fake_patient = SimpleNamespace(id=1, name="张三")

    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(
            Intent.add_record,
            patient_name="张三",
            structured_fields={"chief_complaint": "胸痛"},
        )),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patient_by_name",
        new=AsyncMock(return_value=fake_patient),
    ), patch(
        "routers.records.save_record",
        new=AsyncMock(),
    ) as mock_save:
        resp = await records.chat(records.ChatInput(text="张三胸痛", doctor_id=DOCTOR))

    assert resp.pending_approval_id is None
    mock_save.assert_called_once()
