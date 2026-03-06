from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import routers.records as records
from models.medical_record import MedicalRecord
from services.errors import InvalidMedicalRecordError
from services.miniprogram_auth import issue_miniprogram_token
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
    assert records._leading_name_with_clinical_context("张三，男，52岁，胸闷三周") == "张三"
    assert records._leading_name_with_clinical_context("张三") is None
    assert records._contains_clinical_content("反复胸痛，拟复查")
    assert not records._contains_clinical_content("你好")
    assert records._contains_treatment_signal("建议口服阿司匹林")
    assert not records._contains_treatment_signal("头痛两天，睡眠差")
    assert records._parse_delete_patient_target("删除患者ID 12") == (12, None, None)
    assert records._parse_delete_patient_target("删除第二个患者章三") == (None, "章三", 2)
    assert records._parse_delete_patient_target("删除患者章三") == (None, "章三", None)
    assert records._parse_schedule_appointment_target("给张三安排预约 2026-03-15T14:00:00") == ("张三", "2026-03-15T14:00:00")
    assert records._parse_schedule_appointment_target("为张三安排复诊 2026年3月15日14:00") == ("张三", "2026-03-15T14:00:00")


async def test_chat_empty_text_raises_422():
    with pytest.raises(HTTPException) as exc:
        await records.chat(records.ChatInput(text="   "))
    assert exc.value.status_code == 422


def test_resolve_doctor_id_uses_bearer_token_over_body():
    token = issue_miniprogram_token("doctor_from_token", channel="wechat_mini")["access_token"]
    resolved = records._resolve_doctor_id(
        records.ChatInput(text="你好", doctor_id="doctor_from_body"),
        f"Bearer {token}",
    )
    assert resolved == "doctor_from_token"


def test_resolve_doctor_id_requires_auth_when_fallback_disabled(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("RECORDS_CHAT_ALLOW_BODY_DOCTOR_ID", "false")
    with pytest.raises(HTTPException) as exc:
        records._resolve_doctor_id(records.ChatInput(text="你好", doctor_id=DOCTOR), None)
    assert exc.value.status_code == 401


def test_enforce_rate_limit_raises_429():
    records._RATE_WINDOWS.clear()
    original_limit = records._REQUESTS_PER_MINUTE
    records._REQUESTS_PER_MINUTE = 1
    try:
        records._enforce_rate_limit("doc-limit-1")
        with pytest.raises(HTTPException) as exc:
            records._enforce_rate_limit("doc-limit-1")
        assert exc.value.status_code == 429
    finally:
        records._REQUESTS_PER_MINUTE = original_limit


async def test_chat_dispatch_errors_map_to_429_and_503():
    with patch("routers.records.agent_dispatch", new=AsyncMock(side_effect=RuntimeError("429 rate_limit"))):
        with pytest.raises(HTTPException) as exc:
            await records.chat(records.ChatInput(text="x", doctor_id=DOCTOR))
    assert exc.value.status_code == 429

    with patch("routers.records.agent_dispatch", new=AsyncMock(side_effect=RuntimeError("service down"))):
        with pytest.raises(HTTPException) as exc2:
            await records.chat(records.ChatInput(text="x", doctor_id=DOCTOR))
    assert exc2.value.status_code == 503


async def test_chat_patient_count_fastpath_returns_real_count_and_skips_agent():
    fake_db = object()
    agent_mock = AsyncMock()
    patients = [SimpleNamespace(id=1, name="张三"), SimpleNamespace(id=2, name="李四")]
    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.get_all_patients",
        new=AsyncMock(return_value=patients),
    ), patch("routers.records.agent_dispatch", new=agent_mock):
        resp = await records.chat(records.ChatInput(text="我现有多少病人", doctor_id=DOCTOR))

    agent_mock.assert_not_awaited()
    assert "患者数量：2" in resp.reply


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

    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.create_patient, patient_name="李明", gender="男", age=40)),
    ), patch(
        "routers.records.db_create_patient",
        new=AsyncMock(side_effect=InvalidMedicalRecordError("invalid")),
    ):
        resp3 = await records.chat(records.ChatInput(text="建档李明", doctor_id=DOCTOR))
    assert "格式不正确" in resp3.reply


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


async def test_chat_add_record_clears_hallucinated_treatment_when_no_signal():
    fake_db = object()
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(
            return_value=_intent(
                Intent.add_record,
                patient_name="尹晴",
                structured_fields={
                    "chief_complaint": "头痛2天",
                    "diagnosis": "偏头痛待排",
                    "treatment_plan": "建议休息，必要时使用止痛药",
                },
            )
        ),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patient_by_name",
        new=AsyncMock(return_value=SimpleNamespace(id=9, name="尹晴")),
    ), patch(
        "routers.records.save_record",
        new=AsyncMock(return_value=SimpleNamespace(id=101)),
    ):
        resp = await records.chat(records.ChatInput(text="尹晴，女，60岁，头痛2天，睡眠差。", doctor_id=DOCTOR))

    assert resp.record is not None
    assert resp.record.treatment_plan is None


async def test_chat_force_add_record_when_intent_drifts_but_text_is_clinical():
    fake_db = object()
    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.unknown, patient_name=None, chat_reply=None)),
    ), patch(
        "routers.records.structure_medical_record",
        new=AsyncMock(return_value=_record()),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patient_by_name",
        new=AsyncMock(return_value=SimpleNamespace(id=7, name="钱芳")),
    ), patch(
        "routers.records.save_record",
        new=AsyncMock(return_value=SimpleNamespace(id=100)),
    ) as mock_save:
        resp = await records.chat(records.ChatInput(text="钱芳，女，63岁，反复胸闷3天", doctor_id=DOCTOR))

    assert "保存病历" in resp.reply
    assert resp.record is not None
    assert mock_save.await_count == 1


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
    assert "不能确定您的操作意图" in resp3.reply

    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.unknown, chat_reply=None)),
    ):
        resp4 = await records.chat(records.ChatInput(text="hi", doctor_id=DOCTOR))
    assert "不能确定您的操作意图" in resp4.reply


async def test_chat_delete_patient_fastpath_and_intent_branches():
    fake_db = object()
    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.delete_patient_for_doctor",
        new=AsyncMock(return_value=None),
    ):
        resp = await records.chat(records.ChatInput(text="删除患者ID 99", doctor_id=DOCTOR))
    assert "未找到患者 ID 99" in resp.reply

    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patients_by_exact_name",
        new=AsyncMock(return_value=[SimpleNamespace(id=1, name="章三"), SimpleNamespace(id=2, name="章三")]),
    ):
        resp2 = await records.chat(records.ChatInput(text="删除患者章三", doctor_id=DOCTOR))
    assert "同名患者" in resp2.reply

    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patients_by_exact_name",
        new=AsyncMock(return_value=[SimpleNamespace(id=1, name="章三"), SimpleNamespace(id=2, name="章三")]),
    ), patch(
        "routers.records.delete_patient_for_doctor",
        new=AsyncMock(return_value=SimpleNamespace(id=2, name="章三")),
    ):
        resp3 = await records.chat(records.ChatInput(text="删除第二个患者章三", doctor_id=DOCTOR))
    assert "已删除患者【章三】(ID 2)" in resp3.reply

    with patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.delete_patient, patient_name="张三", extra_data={"occurrence_index": 1})),
    ), patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patients_by_exact_name",
        new=AsyncMock(return_value=[SimpleNamespace(id=6, name="张三")]),
    ), patch(
        "routers.records.delete_patient_for_doctor",
        new=AsyncMock(return_value=SimpleNamespace(id=6, name="张三")),
    ):
        resp4 = await records.chat(records.ChatInput(text="请删除张三", doctor_id=DOCTOR))
    assert "已删除患者【张三】" in resp4.reply


async def test_chat_schedule_appointment_and_save_context_fastpaths():
    fake_db = object()
    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.find_patient_by_name",
        new=AsyncMock(return_value=SimpleNamespace(id=8, name="张三")),
    ), patch(
        "routers.records.create_appointment_task",
        new=AsyncMock(return_value=SimpleNamespace(id=77)),
    ):
        resp = await records.chat(records.ChatInput(text="给张三安排预约 2026-03-15T14:00:00", doctor_id=DOCTOR))
    assert "任务编号：77" in resp.reply

    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.upsert_doctor_context",
        new=AsyncMock(),
    ) as upsert_ctx:
        resp2 = await records.chat(records.ChatInput(text="总结上下文：近期以胸痛随访为主", doctor_id=DOCTOR))
    assert "已保存医生上下文摘要" in resp2.reply
    upsert_ctx.assert_awaited_once()


async def test_chat_add_to_knowledge_base_fastpath():
    fake_db = object()
    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.save_knowledge_item",
        new=AsyncMock(return_value=SimpleNamespace(id=12, content="胸痛先排除ACS")),
    ) as add_knowledge, patch("routers.records.agent_dispatch", new=AsyncMock()) as agent_mock:
        resp = await records.chat(
            records.ChatInput(text="add_to_knowledge_base 胸痛先排除ACS", doctor_id=DOCTOR)
        )

    assert "已加入医生知识库（#12）" in resp.reply
    add_knowledge.assert_awaited_once()
    agent_mock.assert_not_awaited()


async def test_chat_dispatch_passes_knowledge_context():
    fake_db = object()
    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.load_knowledge_context_for_prompt",
        new=AsyncMock(return_value="【医生知识库（仅作背景约束）】\n1. 胸痛先排除ACS"),
    ) as load_ctx, patch(
        "routers.records.agent_dispatch",
        new=AsyncMock(return_value=_intent(Intent.unknown, chat_reply="你好")),
    ) as dispatch_mock:
        resp = await records.chat(records.ChatInput(text="今天门诊有点忙", doctor_id=DOCTOR))

    load_ctx.assert_awaited_once()
    assert dispatch_mock.await_args.kwargs["knowledge_context"].startswith("【医生知识库")
    assert "不能确定您的操作意图" in resp.reply


async def test_chat_notify_control_commands_fastpath():
    with patch(
        "routers.records.set_notify_mode",
        new=AsyncMock(return_value=SimpleNamespace(notify_mode="manual")),
    ):
        resp = await records.chat(records.ChatInput(text="通知模式 手动", doctor_id=DOCTOR))
    assert "通知模式已更新" in resp.reply

    with patch(
        "routers.records.set_notify_interval",
        new=AsyncMock(return_value=SimpleNamespace(interval_minutes=30)),
    ):
        resp2 = await records.chat(records.ChatInput(text="通知频率 每30分钟", doctor_id=DOCTOR))
    assert "每30分钟" in resp2.reply

    with patch(
        "routers.records.run_due_task_cycle",
        new=AsyncMock(return_value={"due_count": 2, "eligible_count": 2, "sent_count": 1, "failed_count": 1}),
    ):
        resp3 = await records.chat(records.ChatInput(text="立即发送待办", doctor_id=DOCTOR))
    assert "sent=1" in resp3.reply


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
