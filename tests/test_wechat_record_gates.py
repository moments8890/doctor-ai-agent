"""微信病历确认门与媒体后台处理单元测试：覆盖文件/语音/图片背景任务、病历结构化及确认/撤销流程。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import routers.wechat as wechat
from db.models.medical_record import MedicalRecord
from services.ai.intent import Intent, IntentResult
from services.session import set_pending_create


DOCTOR = "wechat_routes_doc"


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
    with patch("routers.wechat._get_access_token", new=AsyncMock(side_effect=RuntimeError("no token"))), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg2:
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
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_media", new=AsyncMock(return_value=b"%PDF-1.7")), \
         patch("routers.wechat.extract_text_from_pdf", return_value="章三 偏头痛 3天"), \
         patch("routers.wechat._handle_intent_bg", new=AsyncMock()) as intent_bg, \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_pdf_file_bg("m-pdf", "case.pdf", DOCTOR, open_kfid="kf1")
    intent_bg.assert_awaited_once()
    send_msg.assert_not_awaited()


async def test_file_bg_detects_pdf_by_header_without_pdf_extension():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_media", new=AsyncMock(return_value=b"%PDF-1.7\n...")), \
         patch("routers.wechat._handle_pdf_file_bg", new=AsyncMock()) as pdf_bg:
        await wechat._handle_file_bg("m-file", "文件", DOCTOR, open_kfid="kf1")
    pdf_bg.assert_awaited_once()


async def test_file_bg_non_pdf_sends_notice():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_media", new=AsyncMock(return_value=b"PK\x03\x04...")), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_file_bg("m-file", "报告.docx", DOCTOR, open_kfid="kf1")
    send_msg.assert_awaited_once()


async def test_file_bg_download_failure_sends_generic_error():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_media", new=AsyncMock(side_effect=RuntimeError("network secret"))), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_file_bg("m-file", "报告.docx", DOCTOR, open_kfid="kf1")
    send_msg.assert_awaited_once()
    msg = send_msg.await_args.args[1]
    assert "文件下载失败" in msg
    assert "network secret" not in msg


async def test_pdf_file_bg_failure_sends_error_notice():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_media", new=AsyncMock(return_value=b"%PDF-1.7")), \
         patch("routers.wechat.extract_text_from_pdf", side_effect=RuntimeError("pdftotext failed")), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_pdf_file_bg("m-pdf", "case.pdf", DOCTOR, open_kfid="kf1")
    send_msg.assert_awaited_once()
    pdf_msg = send_msg.await_args.args[1]
    assert "PDF解析失败" in pdf_msg
    assert "pdftotext failed" not in pdf_msg


# ---------------------------------------------------------------------------
# _handle_add_record structured-fields path tests
# ---------------------------------------------------------------------------


async def test_handle_add_record_uses_structured_fields(session_factory):
    """When structured_fields is set, structure_medical_record should NOT be called.
    Normal records now go through the confirmation gate — returns a draft preview."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        structured_fields={"content": "头痛两天 紧张性头痛", "tags": ["紧张性头痛"]},
        chat_reply="好的，张三头痛两天的情况记下来了。",
    )
    structure_mock = AsyncMock()
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", structure_mock):
        reply = await wechat._handle_add_record("张三头痛两天", DOCTOR, intent)
    structure_mock.assert_not_called()
    assert "记录" in reply or "撤销" in reply
    assert "张三" in reply


async def test_handle_add_record_falls_back_to_structuring_llm(session_factory):
    """When structured_fields is None, structure_medical_record should be called."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        structured_fields=None,
        chat_reply=None,
    )
    fake_record = MedicalRecord(content="头痛 偏头痛", tags=["偏头痛"])
    structure_mock = AsyncMock(return_value=fake_record)
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", structure_mock):
        reply = await wechat._handle_add_record("张三头痛两天", DOCTOR, intent)
    structure_mock.assert_called_once()
    assert "张三" in reply or "病历" in reply


async def test_handle_add_record_uses_chat_reply_from_intent(session_factory):
    """Normal records go through the confirmation gate — returns draft preview, not chat_reply."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="李明",
        structured_fields={"content": "发烧三天"},
        chat_reply="李明发烧三天，退烧药已记录。",
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_add_record("李明发烧三天", DOCTOR, intent)
    assert "记录" in reply or "撤销" in reply
    assert "李明" in reply


async def test_handle_add_record_fallback_reply_when_no_chat_reply(session_factory):
    """When chat_reply is None, reply should contain patient name."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="王五",
        structured_fields={"content": "腹痛"},
        chat_reply=None,
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_add_record("王五腹痛", DOCTOR, intent)
    assert "王五" in reply


async def test_handle_add_record_emergency_prefix(session_factory):
    """Emergency records should have 🚨 prefix regardless of chat_reply."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="韩伟",
        is_emergency=True,
        structured_fields={"content": "STEMI急诊"},
        chat_reply="韩伟STEMI已记录，绿色通道已启动。",
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.create_emergency_task", new=AsyncMock()):
        reply = await wechat._handle_add_record("韩伟STEMI", DOCTOR, intent)
    assert reply.startswith("🚨")


async def test_handle_add_record_structuring_value_error_returns_natural_msg(session_factory):
    """ValueError in structure_medical_record returns natural error message."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        structured_fields=None,
        chat_reply=None,
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(side_effect=ValueError("bad"))):
        reply = await wechat._handle_add_record("不完整的输入", DOCTOR, intent)
    assert "没能识别" in reply


async def test_handle_add_record_structuring_generic_error_returns_natural_msg(session_factory):
    """Generic exception in structure_medical_record returns natural error message."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        structured_fields=None,
        chat_reply=None,
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.domain.record_ops.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("boom"))):
        reply = await wechat._handle_add_record("张三胸痛", DOCTOR, intent)
    assert "不好意思" in reply or "出了点问题" in reply


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

    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("services.wechat.wechat_domain.AsyncSessionLocal", session_factory), \
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

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_pending_record_reply("取消", DOCTOR, sess)

    assert "撤销" in reply or "放弃" in reply or "取消" in reply
    assert _gs(DOCTOR).pending_record_id is None


async def test_handle_pending_record_reply_expired_draft(session_factory):
    """Replying 确认 when draft doesn't exist returns error and clears state."""
    from services.session import set_pending_record_id, get_session as _gs

    set_pending_record_id(DOCTOR, "nonexistentdraft")
    sess = _gs(DOCTOR)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_pending_record_reply("确认", DOCTOR, sess)

    assert "过期" in reply or "不存在" in reply or "失败" in reply
    assert _gs(DOCTOR).pending_record_id is None
