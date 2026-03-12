"""病历路由单元测试：覆盖病历创建、查询、更新和语音/图像录入端点的完整路径。"""

from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi import HTTPException

import routers.records as records
from db.models.medical_record import MedicalRecord
from utils.errors import InvalidMedicalRecordError
from services.ai.intent import Intent, IntentResult
from services.domain.intent_handlers._types import HandlerResult
from services.domain.name_utils import leading_name_with_clinical_context as _leading_name_with_clinical_context
from services.session import reset_session_state_for_tests


DOCTOR = "records_router_doc"


# ── Autouse fixture: clear session state between tests ────────────────────────
# Several tests set current_patient / candidate via the workflow. Without
# cleanup the in-memory session leaks into the next test, causing false
# failures (e.g. a query_records test inherits a patient from add_record).

@pytest.fixture(autouse=True)
def _clear_session():
    reset_session_state_for_tests()
    yield
    reset_session_state_for_tests()


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
    return MedicalRecord(content="胸痛 冠心病 随访", tags=["冠心病"])


def _intent(intent: Intent, **kwargs) -> IntentResult:
    return IntentResult(intent=intent, **kwargs)


def test_helper_name_validation_and_parsing():
    assert records._is_valid_patient_name("张三")
    assert not records._is_valid_patient_name("  ")
    assert not records._is_valid_patient_name("这位患者叫什么名字")
    assert not records._is_valid_patient_name("张" * 25)

    from services.domain.name_utils import assistant_asked_for_name, name_only_text
    history = [{"role": "assistant", "content": "请问这位患者叫什么名字？"}]
    assert assistant_asked_for_name(history) is True
    assert assistant_asked_for_name([{"role": "user", "content": "x"}]) is False
    assert name_only_text("陈明") == "陈明"
    assert name_only_text("陈明，胸痛") is None
    assert _leading_name_with_clinical_context("张三，男，52岁，胸闷三周") == "张三"
    assert _leading_name_with_clinical_context("张三") is None
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


def test_resolve_doctor_id_uses_bearer_token_over_body(monkeypatch):
    monkeypatch.setenv("MINIPROGRAM_TOKEN_SECRET", "test-secret-for-unit-tests")
    from services.auth.miniprogram_auth import issue_miniprogram_token
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
    # Patch at the source module — chat_core now uses the intent workflow which
    # imports dispatch from services.ai.agent inside the classifier function.
    with patch("services.ai.agent.dispatch", new=AsyncMock(side_effect=RuntimeError("429 rate_limit"))):
        with pytest.raises(HTTPException) as exc:
            await records.chat(records.ChatInput(text="x", doctor_id=DOCTOR))
    assert exc.value.status_code == 429
    assert exc.value.detail == "rate_limit_exceeded"

    with patch("services.ai.agent.dispatch", new=AsyncMock(side_effect=RuntimeError("service down"))):
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
    ), patch("services.ai.agent.dispatch", new=agent_mock):
        resp = await records.chat(records.ChatInput(text="我现有多少病人", doctor_id=DOCTOR))

    agent_mock.assert_not_awaited()
    assert "患者数量：2" in resp.reply


async def test_chat_create_patient_no_name_and_success():
    # Case 1: no name → shared handler returns ask-for-name reply
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.create_patient, patient_name=None)),
    ), patch("routers.records.shared_handle_create_patient",
             new=AsyncMock(return_value=HandlerResult(reply="好的，请告诉我患者的姓名。"))):
        resp = await records.chat(records.ChatInput(text="创建", doctor_id=DOCTOR))
    assert "姓名" in resp.reply

    # Case 2: name provided → shared handler creates patient
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.create_patient, patient_name="李明", gender="男", age=40)),
    ), patch("routers.records.shared_handle_create_patient",
             new=AsyncMock(return_value=HandlerResult(reply="✅ 已为患者【李明】创建（男、40岁）。"))):
        resp2 = await records.chat(records.ChatInput(text="创建李明", doctor_id=DOCTOR))
    assert "创建" in resp2.reply or "李明" in resp2.reply

    # Case 3: validation error → shared handler returns error reply
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.create_patient, patient_name="李明", gender="男", age=40)),
    ), patch("routers.records.shared_handle_create_patient",
             new=AsyncMock(return_value=HandlerResult(reply="⚠️ 患者信息不完整或格式不正确，请检查后重试。"))):
        resp3 = await records.chat(records.ChatInput(text="创建李明", doctor_id=DOCTOR))
    assert "格式不正确" in resp3.reply


async def test_chat_add_record_invalid_name_and_structuring_error():
    """add_record with patient_name=None asks for name; structuring error returns failure."""
    # Case 1: no patient name → shared handler asks for name
    _doc = "add_record_test_no_name"
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.add_record, patient_name=None)),
    ), patch("routers.records.shared_handle_add_record",
             new=AsyncMock(return_value=HandlerResult(reply="请问这位患者叫什么名字？"))):
        resp = await records.chat(records.ChatInput(text="胸痛", doctor_id=_doc))
    assert "叫什么名字" in resp.reply

    # Case 2: structuring error → shared handler returns error reply
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.add_record, patient_name="张三")),
    ), patch("routers.records.shared_handle_add_record",
             new=AsyncMock(return_value=HandlerResult(reply="病历生成失败，请稍后重试。"))):
        resp2 = await records.chat(records.ChatInput(text="张三胸痛", doctor_id=DOCTOR))
    assert "病历生成失败" in resp2.reply
    assert "llm down" not in resp2.reply


async def test_chat_add_record_clears_hallucinated_treatment_when_no_signal():
    """add_record with structured_fields creates a pending draft (treatment stripped)."""
    from db.models.medical_record import MedicalRecord as _MR
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(
            return_value=_intent(
                Intent.add_record,
                patient_name="尹晴",
                structured_fields={
                    "content": "头痛2天，偏头痛待排",
                    "tags": ["偏头痛待排"],
                },
            )
        ),
    ), patch("routers.records.shared_handle_add_record",
             new=AsyncMock(return_value=HandlerResult(
                 reply="📋 已为【尹晴】生成病历草稿，请确认后保存。",
                 record=_MR(content="头痛2天，偏头痛待排"),
                 pending_id="draft-test",
             ))):
        resp = await records.chat(records.ChatInput(text="尹晴，女，60岁，头痛2天，睡眠差。", doctor_id=DOCTOR))

    assert resp.record is not None
    assert "头痛" in resp.record.content


async def test_chat_force_add_record_when_intent_drifts_but_text_is_clinical():
    """When intent drifts to unknown but text is clinical, the workflow may still produce add_record."""
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.add_record, patient_name="钱芳")),
    ), patch("routers.records.shared_handle_add_record",
             new=AsyncMock(return_value=HandlerResult(
                 reply="📋 已为【钱芳】生成病历草稿，请确认后保存。",
                 record=_record(),
                 pending_id="draft-test",
             ))):
        resp = await records.chat(records.ChatInput(text="钱芳，女，63岁，反复胸闷3天", doctor_id=DOCTOR))

    assert resp.record is not None
    assert "钱芳" in resp.reply


async def test_chat_query_records_named_patient_branches():
    # Case 1: patient not found → shared handler returns not-found reply
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name="张三")),
    ), patch("routers.records.shared_handle_query_records",
             new=AsyncMock(return_value=HandlerResult(reply="未找到患者【张三】。"))):
        resp = await records.chat(records.ChatInput(text="查张三", doctor_id=DOCTOR))
    assert "未找到患者" in resp.reply

    # Case 2: patient found but no records
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name="张三")),
    ), patch("routers.records.shared_handle_query_records",
             new=AsyncMock(return_value=HandlerResult(reply="📂 患者【张三】暂无历史记录。"))):
        resp2 = await records.chat(records.ChatInput(text="查张三", doctor_id=DOCTOR))
    assert "暂无历史记录" in resp2.reply

    # Case 3: patient found with records
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name="张三")),
    ), patch("routers.records.shared_handle_query_records",
             new=AsyncMock(return_value=HandlerResult(
                 reply="📂 患者【张三】最近 1 条记录：\n1. [2026-03-02] 胸痛 冠心病",
             ))):
        resp3 = await records.chat(records.ChatInput(text="查张三", doctor_id=DOCTOR))
    assert "最近 1 条记录" in resp3.reply


async def test_chat_query_records_all_doctor_records_branches():
    # Case 1: no records → shared handler returns empty message
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name=None)),
    ), patch("routers.records.shared_handle_query_records",
             new=AsyncMock(return_value=HandlerResult(reply="📂 暂无任何病历记录。"))):
        resp4 = await records.chat(records.ChatInput(text="查病历", doctor_id=DOCTOR))
    assert "暂无任何病历记录" in resp4.reply

    # Case 2: has records
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.query_records, patient_name=None)),
    ), patch("routers.records.shared_handle_query_records",
             new=AsyncMock(return_value=HandlerResult(
                 reply="📂 最近 1 条记录：\n【未关联】[—] —",
             ))):
        resp5 = await records.chat(records.ChatInput(text="查病历", doctor_id=DOCTOR))
    assert "最近 1 条记录" in resp5.reply


async def test_chat_list_patients_and_unknown_reply():
    # Case 1: no patients → shared handler returns empty message
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.list_patients)),
    ), patch("routers.records.shared_handle_list_patients",
             new=AsyncMock(return_value=HandlerResult(reply="📂 暂无患者记录。"))):
        resp = await records.chat(records.ChatInput(text="所有患者", doctor_id=DOCTOR))
    assert "暂无患者记录" in resp.reply

    # Case 2: has patients → shared handler returns patient list
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.list_patients)),
    ), patch("routers.records.shared_handle_list_patients",
             new=AsyncMock(return_value=HandlerResult(reply="👥 共 1 位患者：\n1. 张三（男、46岁）"))):
        resp2 = await records.chat(records.ChatInput(text="所有患者", doctor_id=DOCTOR))
    assert "共 1 位患者" in resp2.reply
    assert "张三" in resp2.reply

    # Case 3: "hi" matches greeting fast path → warm welcome
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.unknown, chat_reply="你好医生")),
    ):
        resp3 = await records.chat(records.ChatInput(text="hi", doctor_id=DOCTOR))
    assert "专属医助" in resp3.reply

    # Case 4: "hi" without chat_reply → same greeting path
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.unknown, chat_reply=None)),
    ):
        resp4 = await records.chat(records.ChatInput(text="hi", doctor_id=DOCTOR))
    assert "专属医助" in resp4.reply


async def test_chat_delete_patient_fastpath_and_intent_branches():
    fake_db = object()
    # Case 1: delete by ID — not found (this is a fast path in records.py, not a shared handler)
    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "services.domain.chat_handlers.delete_patient_for_doctor",
        new=AsyncMock(return_value=None),
    ):
        resp = await records.chat(records.ChatInput(text="删除患者ID 99", doctor_id=DOCTOR))
    assert "未找到患者 ID 99" in resp.reply

    # Case 2: delete by name — multiple same-name matches → clarification
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.delete_patient, patient_name="章三")),
    ), patch("routers.records.shared_handle_delete_patient",
             new=AsyncMock(return_value=HandlerResult(
                 reply="⚠️ 找到同名患者【章三】共 2 位，请发送「删除第2个患者章三」这类指令。"
             ))):
        resp2 = await records.chat(records.ChatInput(text="删除患者章三", doctor_id=DOCTOR))
    assert "同名患者" in resp2.reply

    # Case 3: delete with ordinal — success
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.delete_patient, patient_name="章三", extra_data={"occurrence_index": 2})),
    ), patch("routers.records.shared_handle_delete_patient",
             new=AsyncMock(return_value=HandlerResult(reply="✅ 已删除患者【章三】及其相关记录。"))):
        resp3 = await records.chat(records.ChatInput(text="删除第二个患者章三", doctor_id=DOCTOR))
    assert "已删除患者【章三】" in resp3.reply

    # Case 4: delete via intent dispatch — success
    reset_session_state_for_tests()
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.delete_patient, patient_name="张三", extra_data={"occurrence_index": 1})),
    ), patch("routers.records.shared_handle_delete_patient",
             new=AsyncMock(return_value=HandlerResult(reply="✅ 已删除患者【张三】及其相关记录。"))):
        resp4 = await records.chat(records.ChatInput(text="请删除张三", doctor_id=DOCTOR))
    assert "已删除患者【张三】" in resp4.reply


async def test_chat_schedule_appointment_and_save_context_fastpaths():
    fake_db = object()
    # Schedule appointment — mock the shared handler
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(
            Intent.schedule_appointment,
            patient_name="张三",
            extra_data={"appointment_time": "2026-03-15T14:00:00"},
        )),
    ), patch("routers.records.shared_handle_schedule_appointment",
             new=AsyncMock(return_value=HandlerResult(
                 reply="📅 已为患者【张三】安排预约\n预约时间：2026-03-15 14:00\n任务编号：77（将在1小时前提醒）",
             ))):
        resp = await records.chat(records.ChatInput(text="给张三安排预约 2026-03-15T14:00:00", doctor_id=DOCTOR))
    assert "任务编号：77" in resp.reply

    reset_session_state_for_tests()
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
    ) as add_knowledge, patch("services.ai.agent.dispatch", new=AsyncMock()) as agent_mock:
        resp = await records.chat(
            records.ChatInput(text="add_to_knowledge_base 胸痛先排除ACS", doctor_id=DOCTOR)
        )

    assert "已加入医生知识库（#12）" in resp.reply
    add_knowledge.assert_awaited_once()
    agent_mock.assert_not_awaited()


async def test_chat_dispatch_passes_knowledge_context():
    """Verify that knowledge_context is loaded and passed through the workflow to the LLM."""
    fake_db = object()
    with patch("routers.records.AsyncSessionLocal", return_value=_SessionCtx(fake_db)), patch(
        "routers.records.load_knowledge_context_for_prompt",
        new=AsyncMock(return_value="【医生知识库（仅作背景约束）】\n1. 胸痛先排除ACS"),
    ) as load_ctx, patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=_intent(Intent.unknown, chat_reply="你好")),
    ) as dispatch_mock:
        resp = await records.chat(records.ChatInput(text="今天门诊有点忙", doctor_id=DOCTOR))

    load_ctx.assert_awaited_once()
    # The knowledge_context is now passed through the workflow to the classifier,
    # which passes it as a kwarg to agent_dispatch.
    assert dispatch_mock.await_args.kwargs["knowledge_context"].startswith("【医生知识库")
    # intent_result.chat_reply="你好" is short (< 6 chars) so _build_unclear_reply falls back
    # to the unclear intent reply (echo of user text or default).
    assert "没太理解" in resp.reply or "今天门诊" in resp.reply


async def test_chat_notify_control_commands_fastpath():
    """Notify control commands are handled before intent routing."""
    # The notify control functions are now in services.domain.chat_handlers
    # and are imported by routers.records as _handle_notify_control_command.
    # The inner functions (set_notify_mode, etc.) are in services.notify.notify_control.
    with patch(
        "services.notify.notify_control.set_notify_mode",
        new=AsyncMock(return_value=SimpleNamespace(notify_mode="manual")),
    ):
        resp = await records.chat(records.ChatInput(text="通知模式 手动", doctor_id=DOCTOR))
    assert "通知模式已更新" in resp.reply

    with patch(
        "services.notify.notify_control.set_notify_interval",
        new=AsyncMock(return_value=SimpleNamespace(interval_minutes=30)),
    ):
        resp2 = await records.chat(records.ChatInput(text="通知频率 每30分钟", doctor_id=DOCTOR))
    assert "每30分钟" in resp2.reply

    with patch(
        "services.domain.chat_handlers.run_due_task_cycle",
        new=AsyncMock(return_value={"due_count": 2, "eligible_count": 2, "sent_count": 1, "failed_count": 1}),
    ):
        resp3 = await records.chat(records.ChatInput(text="立即发送待办", doctor_id=DOCTOR))
    assert "sent=1" in resp3.reply


async def test_create_record_from_text_endpoint():
    with pytest.raises(HTTPException) as exc:
        await records.create_record_from_text(records.TextInput(text=" "))
    assert exc.value.status_code == 422

    with patch("routers.records.structure_medical_record", new=AsyncMock(return_value=_record())):
        rec = await records.create_record_from_text(records.TextInput(text="胸痛"))
    assert "胸痛" in rec.content

    with patch("routers.records.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(HTTPException) as exc2:
            await records.create_record_from_text(records.TextInput(text="胸痛"))
    assert exc2.value.status_code == 500
    assert exc2.value.detail == "Internal server error"

    with patch("routers.records.structure_medical_record", new=AsyncMock(side_effect=ValueError("bad input"))):
        with pytest.raises(HTTPException) as exc2b:
            await records.create_record_from_text(records.TextInput(text="胸痛"))
    assert exc2b.value.status_code == 422
    assert exc2b.value.detail == "Invalid medical record content"


async def test_create_record_from_image_endpoint():
    """ADR 0009: /from-image now OCRs then routes to import_history."""
    DOCTOR = "test_records_doc"

    # Unsupported type → 422
    with pytest.raises(HTTPException) as exc3:
        await records.create_record_from_image(
            image=_Upload(content_type="image/tiff"), doctor_id=DOCTOR,
        )
    assert exc3.value.status_code == 422

    # Success → returns import reply
    import_mock = AsyncMock(return_value="已导入 1 条病历记录")
    with patch("routers.records.extract_text_from_image", new=AsyncMock(return_value="识别文本")), \
         patch("routers.records._import_extracted_text", new=import_mock):
        result = await records.create_record_from_image(
            image=_Upload(content_type="image/png", data=b"img"), doctor_id=DOCTOR,
        )
    assert result["reply"] == "已导入 1 条病历记录"
    assert result["source"] == "image"

    # OCR failure → 500
    with patch("routers.records.extract_text_from_image", new=AsyncMock(side_effect=RuntimeError("ocr fail"))):
        with pytest.raises(HTTPException) as exc4:
            await records.create_record_from_image(
                image=_Upload(content_type="image/png", data=b"img"), doctor_id=DOCTOR,
            )
    assert exc4.value.status_code == 500

    # Empty OCR → 422
    with patch("routers.records.extract_text_from_image", new=AsyncMock(return_value="  ")):
        with pytest.raises(HTTPException) as exc4b:
            await records.create_record_from_image(
                image=_Upload(content_type="image/png", data=b"img"), doctor_id=DOCTOR,
            )
    assert exc4b.value.status_code == 422


async def test_create_record_from_audio_endpoint():
    """ADR 0009: /from-audio now transcribes then routes to import_history."""
    DOCTOR = "test_records_doc"

    # Unsupported type → 422
    with pytest.raises(HTTPException) as exc5:
        await records.create_record_from_audio(
            audio=_Upload(content_type="audio/aac"), doctor_id=DOCTOR,
        )
    assert exc5.value.status_code == 422

    # Success → returns import reply
    import_mock = AsyncMock(return_value="已导入 1 条病历记录")
    with patch("routers.records.transcribe_audio", new=AsyncMock(return_value="转写文本")), \
         patch("routers.records._import_extracted_text", new=import_mock):
        result = await records.create_record_from_audio(
            audio=_Upload(content_type="audio/wav", data=b"wav", filename="a.wav"),
            doctor_id=DOCTOR,
        )
    assert result["reply"] == "已导入 1 条病历记录"
    assert result["source"] == "voice"

    # Transcription failure → 500
    with patch("routers.records.transcribe_audio", new=AsyncMock(side_effect=RuntimeError("asr fail"))):
        with pytest.raises(HTTPException) as exc6:
            await records.create_record_from_audio(
                audio=_Upload(content_type="audio/wav", data=b"wav", filename="a.wav"),
                doctor_id=DOCTOR,
            )
    assert exc6.value.status_code == 500

    # Empty transcript → 422
    with patch("routers.records.transcribe_audio", new=AsyncMock(return_value="  ")):
        with pytest.raises(HTTPException) as exc6b:
            await records.create_record_from_audio(
                audio=_Upload(content_type="audio/wav", data=b"wav", filename="a.wav"),
                doctor_id=DOCTOR,
            )
    assert exc6b.value.status_code == 422
