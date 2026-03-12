"""微信病历确认门与媒体后台处理单元测试：覆盖文件/语音/图片背景任务、病历结构化及确认/撤销流程。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import routers.wechat as wechat
import routers.wechat_flows as wechat_flows
from db.models.medical_record import MedicalRecord
from services.ai.intent import Intent, IntentResult
from services.session import set_pending_create


DOCTOR = "wechat_routes_doc"

# Shared handler modules import AsyncSessionLocal at module level;
# we must patch each reference for in-memory SQLite tests.
_SHARED_DB_TARGETS = [
    "routers.wechat.AsyncSessionLocal",
    "routers.wechat_flows.AsyncSessionLocal",
    "services.domain.intent_handlers._simple_intents.AsyncSessionLocal",
    "services.domain.intent_handlers._create_patient.AsyncSessionLocal",
    "services.domain.intent_handlers._add_record.AsyncSessionLocal",
    "services.domain.intent_handlers._query_records.AsyncSessionLocal",
    "services.domain.intent_handlers._confirm_pending.AsyncSessionLocal",
    "services.wechat.wechat_domain.AsyncSessionLocal",
]


import contextlib


@contextlib.contextmanager
def _patch_all_db(session_factory):
    """Patch AsyncSessionLocal in all handler modules at once."""
    patches = [patch(t, session_factory) for t in _SHARED_DB_TARGETS]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()


class DummyLock:
    def locked(self) -> bool:
        return False

    async def acquire(self) -> bool:
        return True

    def release(self) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


# ---------------------------------------------------------------------------
# Voice and image background error path tests
# ---------------------------------------------------------------------------


async def test_voice_and_image_bg_error_paths():
    with patch("routers.wechat._get_access_token", new=AsyncMock(side_effect=RuntimeError("no token"))), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_voice_bg("m1", DOCTOR)
    send_msg.assert_awaited_once()
    voice_msg = send_msg.await_args.args[1]
    assert "语音识别失败" in voice_msg
    assert "no token" not in voice_msg


async def test_image_bg_error_path():
    """Image background processing sends error when access token fails.

    _handle_image_bg delegates to wechat_media_pipeline via wechat_flows;
    we mock the callbacks at the wechat_flows module level where they are
    imported and passed as kwargs to the pipeline function.
    """
    with patch("routers.wechat_flows._get_access_token", new=AsyncMock(side_effect=RuntimeError("no token"))), \
         patch("routers.wechat_flows._send_customer_service_msg", new=AsyncMock()) as send_msg2:
        await wechat._handle_image_bg("m2", DOCTOR)
    send_msg2.assert_awaited_once()
    image_msg = send_msg2.await_args.args[1]
    assert "图片识别失败" in image_msg
    assert "no token" not in image_msg


async def test_voice_bg_pending_create_route_done():
    set_pending_create(DOCTOR, "李雷")
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_and_convert", new=AsyncMock(return_value=b"wav")), \
         patch("routers.wechat.transcribe_audio", new=AsyncMock(return_value="男，40岁")), \
         patch("routers.wechat.get_session_lock", return_value=DummyLock()), \
         patch("routers.wechat.hydrate_session_state", new=AsyncMock()), \
         patch("routers.wechat._handle_pending_create", new=AsyncMock(return_value="ok")), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg, \
         patch("routers.wechat._handle_intent_bg", new=AsyncMock()) as intent_bg:
        await wechat._handle_voice_bg("m3", DOCTOR)
    send_msg.assert_awaited_once()
    intent_bg.assert_not_awaited()


# ---------------------------------------------------------------------------
# PDF and file background tests
# ---------------------------------------------------------------------------


async def test_pdf_file_bg_success_routes_to_intent():
    """Successful PDF extraction routes text to the intent pipeline."""
    intent_bg_mock = AsyncMock()
    send_msg_mock = AsyncMock()
    with patch("routers.wechat_flows._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat_flows.download_media", new=AsyncMock(return_value=b"%PDF-1.7")), \
         patch("routers.wechat_flows.extract_text_from_pdf", return_value="章三 偏头痛 3天"), \
         patch("routers.wechat._handle_intent_bg", new=intent_bg_mock), \
         patch("routers.wechat_flows._send_customer_service_msg", new=send_msg_mock):
        await wechat._handle_pdf_file_bg("m-pdf", "case.pdf", DOCTOR, open_kfid="kf1")
    intent_bg_mock.assert_awaited_once()
    send_msg_mock.assert_not_awaited()


async def test_file_bg_detects_pdf_by_header_without_pdf_extension():
    """A file without .pdf extension but with PDF header is routed to PDF handler."""
    pdf_bg_mock = AsyncMock()
    with patch("routers.wechat_flows._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat_flows.download_media", new=AsyncMock(return_value=b"%PDF-1.7\n...")), \
         patch("routers.wechat_flows.handle_pdf_file_bg", new=pdf_bg_mock):
        await wechat._handle_file_bg("m-file", "文件", DOCTOR, open_kfid="kf1")
    pdf_bg_mock.assert_awaited_once()


async def test_file_bg_non_pdf_sends_notice():
    """Non-PDF/non-Word files send a notice about unsupported type."""
    send_msg_mock = AsyncMock()
    with patch("routers.wechat_flows._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat_flows.download_media", new=AsyncMock(return_value=b"RIFF...")), \
         patch("routers.wechat_flows._send_customer_service_msg", new=send_msg_mock):
        # Use .wav extension — neither PDF nor Word, so unsupported
        await wechat._handle_file_bg("m-file", "报告.wav", DOCTOR, open_kfid="kf1")
    send_msg_mock.assert_awaited_once()


async def test_file_bg_download_failure_sends_generic_error():
    """Download failure sends generic error without leaking internal details."""
    send_msg_mock = AsyncMock()
    with patch("routers.wechat_flows._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat_flows.download_media", new=AsyncMock(side_effect=RuntimeError("network secret"))), \
         patch("routers.wechat_flows._send_customer_service_msg", new=send_msg_mock):
        await wechat._handle_file_bg("m-file", "报告.docx", DOCTOR, open_kfid="kf1")
    send_msg_mock.assert_awaited_once()
    msg = send_msg_mock.await_args.args[1]
    assert "文件下载失败" in msg
    assert "network secret" not in msg


async def test_pdf_file_bg_failure_sends_error_notice():
    """PDF extraction failure sends error notice without leaking exception details."""
    send_msg_mock = AsyncMock()
    with patch("routers.wechat_flows._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat_flows.download_media", new=AsyncMock(return_value=b"%PDF-1.7")), \
         patch("routers.wechat_flows.extract_text_from_pdf", side_effect=RuntimeError("pdftotext failed")), \
         patch("routers.wechat_flows._send_customer_service_msg", new=send_msg_mock):
        await wechat._handle_pdf_file_bg("m-pdf", "case.pdf", DOCTOR, open_kfid="kf1")
    send_msg_mock.assert_awaited_once()
    pdf_msg = send_msg_mock.await_args.args[1]
    assert "PDF解析失败" in pdf_msg
    assert "pdftotext failed" not in pdf_msg


# ---------------------------------------------------------------------------
# _handle_add_record structured-fields path tests
# ---------------------------------------------------------------------------


async def test_handle_add_record_always_calls_structuring_llm(session_factory):
    """ADR 0008: structuring LLM is always called for add_record."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        chat_reply="好的，张三头痛两天的情况记下来了。",
    )
    fake_record = MedicalRecord(content="头痛两天 紧张性头痛", tags=["紧张性头痛"])
    structure_mock = AsyncMock(return_value=fake_record)
    with _patch_all_db(session_factory), \
         patch("services.domain.record_ops.structure_medical_record", structure_mock):
        reply = await wechat._handle_add_record("张三头痛两天", DOCTOR, intent)
    structure_mock.assert_called_once()
    assert "张三" in reply


async def test_handle_add_record_uses_chat_reply_from_intent(session_factory):
    """When chat_reply is provided, shared handler uses it as the draft reply."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="李明",
        chat_reply="李明发烧三天，退烧药已记录。",
    )
    fake_record = MedicalRecord(content="发烧三天")
    with _patch_all_db(session_factory), \
         patch("services.domain.record_ops.structure_medical_record", AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record("李明发烧三天", DOCTOR, intent)
    assert "李明" in reply


async def test_handle_add_record_fallback_reply_when_no_chat_reply(session_factory):
    """When chat_reply is None, reply should contain patient name."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="王五",
        chat_reply=None,
    )
    fake_record = MedicalRecord(content="腹痛")
    with _patch_all_db(session_factory), \
         patch("services.domain.record_ops.structure_medical_record", AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record("王五腹痛", DOCTOR, intent)
    assert "王五" in reply


async def test_handle_add_record_emergency_prefix(session_factory):
    """Emergency records without chat_reply get the default 🚨 prefix."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="韩伟",
        is_emergency=True,
        chat_reply=None,
    )
    fake_record = MedicalRecord(content="STEMI急诊")
    with _patch_all_db(session_factory), \
         patch("services.domain.record_ops.structure_medical_record", AsyncMock(return_value=fake_record)):
        reply = await wechat._handle_add_record("韩伟STEMI", DOCTOR, intent)
    assert "🚨" in reply
    assert "韩伟" in reply


async def test_handle_add_record_structuring_value_error_returns_natural_msg(session_factory):
    """ValueError in structure_medical_record returns natural error message."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        chat_reply=None,
    )
    with _patch_all_db(session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(side_effect=ValueError("bad"))):
        reply = await wechat._handle_add_record("不完整的输入", DOCTOR, intent)
    assert "没能识别" in reply or "病历" in reply


async def test_handle_add_record_structuring_generic_error_returns_natural_msg(session_factory):
    """Generic exception in structure_medical_record returns natural error message."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        chat_reply=None,
    )
    with _patch_all_db(session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("boom"))):
        reply = await wechat._handle_add_record("张三胸痛", DOCTOR, intent)
    assert "不好意思" in reply or "出了点问题" in reply or "失败" in reply


# ---------------------------------------------------------------------------
# Confirmation gate: _handle_pending_record_reply tests
# ---------------------------------------------------------------------------


async def test_handle_pending_record_reply_confirm(session_factory):
    """Replying 确认 saves the pending record and clears session state."""
    from services.session import set_pending_record_id, get_session as _gs
    import json as _json

    from db.crud import create_pending_record as _create_pr

    fake_record = MedicalRecord(content="头痛两天 偏头痛", tags=["偏头痛"])

    async with session_factory() as db:
        await _create_pr(
            db,
            record_id="testdraftabc",
            doctor_id=DOCTOR,
            draft_json=_json.dumps(fake_record.model_dump(), ensure_ascii=False),
            patient_id=None,
            patient_name="张三",
            ttl_minutes=10,
        )

    set_pending_record_id(DOCTOR, "testdraftabc")
    sess = _gs(DOCTOR)

    with _patch_all_db(session_factory), \
         patch("services.wechat.wechat_domain.audit", new=AsyncMock()), \
         patch("services.wechat.wechat_domain.create_follow_up_task", new=AsyncMock()), \
         patch("services.wechat.wechat_domain._bg_auto_learn", new=AsyncMock()):
        reply = await wechat._handle_pending_record_reply("确认", DOCTOR, sess)

    assert "✅" in reply or "已保存" in reply
    assert _gs(DOCTOR).pending_record_id is None


async def test_handle_pending_record_reply_cancel(session_factory):
    """Replying 取消 abandons the pending record and clears session state."""
    from services.session import set_pending_record_id, get_session as _gs
    import json as _json

    from db.crud import create_pending_record as _create_pr

    fake_record = MedicalRecord(content="腹痛")
    async with session_factory() as db:
        await _create_pr(
            db,
            record_id="testdraftcancel",
            doctor_id=DOCTOR,
            draft_json=_json.dumps(fake_record.model_dump(), ensure_ascii=False),
            patient_id=None,
            patient_name="李四",
            ttl_minutes=10,
        )

    set_pending_record_id(DOCTOR, "testdraftcancel")
    sess = _gs(DOCTOR)

    with _patch_all_db(session_factory):
        reply = await wechat._handle_pending_record_reply("取消", DOCTOR, sess)

    assert "撤销" in reply or "放弃" in reply or "取消" in reply
    assert _gs(DOCTOR).pending_record_id is None


async def test_handle_pending_record_reply_expired_draft(session_factory):
    """Replying 确认 when draft doesn't exist clears state and falls back to intent.

    When the pending record is not found in DB, handle_pending_record_reply
    clears the session state and delegates to _handle_intent. We mock
    _handle_intent to avoid an LLM call and verify state is properly cleared.
    """
    from services.session import set_pending_record_id, get_session as _gs
    from routers.wechat_flows import WeChatReply as _WR

    set_pending_record_id(DOCTOR, "nonexistentdraft")
    sess = _gs(DOCTOR)

    with _patch_all_db(session_factory), \
         patch("routers.wechat._handle_intent", new=AsyncMock(return_value=_WR(notification=None, text="fallback"))):
        reply = await wechat._handle_pending_record_reply("确认", DOCTOR, sess)

    # State must be cleared even when draft is missing
    assert _gs(DOCTOR).pending_record_id is None
    # The fallback reply is returned
    assert isinstance(reply, str)
