"""微信路由单元测试：覆盖意图调度、问诊流程、消息路由和签名验证核心流程。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import routers.wechat as wechat
from db.models.medical_record import MedicalRecord
from services.ai.intent import Intent, IntentResult
from services.patient.interview import InterviewState, STEPS
from services.session import (
    clear_pending_create,
    clear_pending_record_id,
    get_session,
    set_pending_create,
)


DOCTOR = "wechat_routes_doc"


class DummyRequest:
    def __init__(self, query_params=None, body=""):
        self.query_params = query_params or {}
        self._body = body.encode("utf-8")

    async def body(self):
        return self._body


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


class FakeTextReply:
    def __init__(self, content, message):
        self.content = content
        self.message = message

    def render(self):
        return self.content


class _SessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


# ---------------------------------------------------------------------------
# Reply builder and interview flow tests
# ---------------------------------------------------------------------------


async def test_build_reply_handles_value_error_and_generic_error():
    with patch("routers.wechat.structure_medical_record", new=AsyncMock(side_effect=ValueError("bad"))):
        msg = await wechat._build_reply("x")
    assert "未能识别" in msg

    with patch("routers.wechat.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("down"))):
        msg2 = await wechat._build_reply("x")
    assert "处理失败" in msg2


async def test_start_interview_and_menu_event_paths():
    text = await wechat._start_interview(DOCTOR)
    assert "开始问诊" in text
    assert "[1/" in text

    with patch("routers.wechat._handle_all_patients", new=AsyncMock(return_value="all")):
        out = await wechat._handle_menu_event("DOCTOR_ALL_PATIENTS", DOCTOR)
    assert out == "all"

    out2 = await wechat._handle_menu_event("UNKNOWN_KEY", DOCTOR)
    assert "菜单" in out2


async def test_handle_interview_step_cancel_and_active():
    sess = get_session(DOCTOR)
    sess.interview = InterviewState()
    result = await wechat._handle_interview_step("取消", DOCTOR)
    assert "问诊结束" in result
    assert get_session(DOCTOR).interview is None

    sess = get_session(DOCTOR)
    sess.interview = InterviewState()
    result2 = await wechat._handle_interview_step("张三", DOCTOR)
    assert "[" in result2
    assert "哪里不舒服" in result2


async def test_handle_interview_step_complete_saves_record(session_factory):
    sess = get_session(DOCTOR)
    iv = InterviewState()
    iv.step = len(STEPS) - 1
    iv.answers = {
        "patient_name": "王五",
        "chief_complaint": "头痛",
        "duration": "2天",
        "severity": "中等",
        "associated_symptoms": "无",
        "past_history": "无",
    }
    sess.interview = iv

    fake_record = MedicalRecord(content="头痛 偏头痛 休息", tags=["偏头痛"])
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        result = await wechat._handle_interview_step("体格检查正常", DOCTOR)

    # Interview completion now routes through confirmation gate — returns draft preview
    assert "草稿" in result or "确认" in result
    assert "王五" in result


# ---------------------------------------------------------------------------
# Name lookup and pending-create tests
# ---------------------------------------------------------------------------


async def test_name_lookup_hit_and_miss(session_factory):
    async with session_factory() as s:
        from db.crud import create_patient
        await create_patient(s, DOCTOR, "李明", None, None)

    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat._handle_query_records", new=AsyncMock(return_value="records")):
        hit = await wechat._handle_name_lookup("李明", DOCTOR)
    assert hit == "records"

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        miss = await wechat._handle_name_lookup("赵六", DOCTOR)
    assert "赵六" in miss
    assert get_session(DOCTOR).pending_create_name == "赵六"


async def test_pending_create_cancel_and_create(session_factory):
    set_pending_create(DOCTOR, "陈明")
    cancelled = await wechat._handle_pending_create("取消", DOCTOR)
    assert "已取消" in cancelled
    assert get_session(DOCTOR).pending_create_name is None

    set_pending_create(DOCTOR, "陈明")
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        created = await wechat._handle_pending_create("男，30岁", DOCTOR)
    assert "创建" in created or "陈明" in created
    assert "30岁" in created
    assert get_session(DOCTOR).pending_create_name is None


async def test_pending_create_requires_gender_or_age(session_factory):
    set_pending_create(DOCTOR, "陈明")
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_pending_create("我又有偏头痛", DOCTOR)
    assert "补充性别和年龄" in reply
    assert get_session(DOCTOR).pending_create_name == "陈明"


async def test_pending_create_reuses_existing_patient_without_duplicate(session_factory):
    async with session_factory() as s:
        from db.crud import create_patient, get_all_patients
        await create_patient(s, DOCTOR, "章三", None, None)
        before = await get_all_patients(s, DOCTOR)
        assert len([p for p in before if p.name == "章三"]) == 1

    set_pending_create(DOCTOR, "章三")
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        out = await wechat._handle_pending_create("男，17岁", DOCTOR)
    assert "章三" in out

    async with session_factory() as s2:
        from db.crud import get_all_patients
        after = await get_all_patients(s2, DOCTOR)
    assert len([p for p in after if p.name == "章三"]) == 1


# ---------------------------------------------------------------------------
# _handle_intent routing tests
# ---------------------------------------------------------------------------


async def test_handle_intent_add_record_asks_for_name_without_session():
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
    ), patch("routers.wechat.get_all_patients", new=AsyncMock(return_value=[])):
        msg = await wechat._handle_intent("发烧一天", DOCTOR)
    assert "叫什么名字" in msg


async def test_handle_intent_add_record_name_token_routes_to_lookup():
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
    ), patch("routers.wechat.get_all_patients", new=AsyncMock(return_value=[])), \
       patch("routers.wechat._handle_name_lookup", new=AsyncMock(return_value="lookup-name")) as lookup_mock:
        msg = await wechat._handle_intent("张三", DOCTOR)
    assert msg == "lookup-name"
    lookup_mock.assert_awaited_once_with("张三", DOCTOR)


async def test_handle_intent_add_record_rebinds_single_patient_when_session_missing(session_factory):
    async with session_factory() as s:
        from db.crud import create_patient
        await create_patient(s, DOCTOR, "张三", None, None)

    sess = get_session(DOCTOR)
    sess.current_patient_id = None
    sess.current_patient_name = None

    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch(
             "services.ai.agent.dispatch",
             new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
         ), \
         patch("routers.wechat._handle_add_record", new=AsyncMock(return_value="saved")) as add_mock:
        msg = await wechat._handle_intent("头疼", DOCTOR)

    assert msg == "saved"
    add_mock.assert_awaited_once()
    assert get_session(DOCTOR).current_patient_name == "张三"


async def test_handle_intent_unknown_no_longer_routes_to_name_lookup():
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply=None)),
    ), patch("routers.wechat._handle_name_lookup", new=AsyncMock(return_value="lookup")):
        out = await wechat._handle_intent("张三", DOCTOR)
    assert "直接描述病历" in out or "无法判断操作意图" in out


async def test_handle_intent_unknown_explicit_name_routes_to_lookup():
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply=None)),
    ), patch("routers.wechat._handle_name_lookup", new=AsyncMock(return_value="name-anchor")) as lookup_mock:
        out = await wechat._handle_intent("我是张三", DOCTOR)
    assert out == "name-anchor"
    lookup_mock.assert_awaited_once_with("张三", DOCTOR)


async def test_handle_intent_unknown_symptom_with_current_patient_saves_brief_record():
    sess = get_session(DOCTOR)
    sess.current_patient_id = 101
    sess.current_patient_name = "章三"
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply=None)),
    ), patch("routers.wechat._handle_add_record", new=AsyncMock(return_value="saved-brief")) as add_mock:
        out = await wechat._handle_intent("我又有偏头痛", DOCTOR)
    assert out == "saved-brief"
    add_mock.assert_awaited_once()


async def test_handle_intent_unknown_greeting_not_routed_as_name():
    with patch(
        "services.ai.agent.dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply=None)),
    ), patch("routers.wechat._handle_name_lookup", new=AsyncMock(return_value="lookup")) as lookup_mock:
        out = await wechat._handle_intent("你好", DOCTOR)

    assert "直接描述病历" in out or "无法判断操作意图" in out
    lookup_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Task-list and schedule intent tests (split from original omnibus test)
# ---------------------------------------------------------------------------


async def test_handle_list_tasks_returns_pending_tasks():
    pending_tasks = [
        SimpleNamespace(id=1, task_type="follow_up", title="随访提醒：张三", due_at=None),
        SimpleNamespace(id=2, task_type="appointment", title="预约提醒：李四", due_at=datetime(2026, 3, 15, 9, 0, 0)),
    ]
    with patch("routers.wechat.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("routers.wechat.list_tasks", new=AsyncMock(return_value=pending_tasks)):
        text = await wechat._handle_list_tasks(DOCTOR)
    assert "待办任务" in text and "follow_up" in text and "appointment" in text


async def test_handle_complete_task_miss_and_hit():
    with patch("routers.wechat.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("routers.wechat.update_task_status", new=AsyncMock(return_value=None)):
        miss = await wechat._handle_complete_task(
            DOCTOR,
            IntentResult(intent=Intent.complete_task, extra_data={"task_id": 999}),
        )
    assert "未找到任务" in miss

    with patch("routers.wechat.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("routers.wechat.update_task_status", new=AsyncMock(return_value=SimpleNamespace(title="随访提醒：张三"))):
        ok = await wechat._handle_complete_task(
            DOCTOR,
            IntentResult(intent=Intent.complete_task, extra_data={"task_id": 1}),
        )
    assert ok  # natural reply (from chat_reply or default)


async def test_handle_schedule_appointment_validation_errors():
    bad_name = await wechat._handle_schedule_appointment(
        DOCTOR,
        IntentResult(intent=Intent.schedule_appointment, patient_name=None, extra_data={}),
    )
    assert "未能识别患者姓名" in bad_name

    bad_time = await wechat._handle_schedule_appointment(
        DOCTOR,
        IntentResult(intent=Intent.schedule_appointment, patient_name="王五", extra_data={}),
    )
    assert "未能识别预约时间" in bad_time

    bad_format = await wechat._handle_schedule_appointment(
        DOCTOR,
        IntentResult(
            intent=Intent.schedule_appointment,
            patient_name="王五",
            extra_data={"appointment_time": "明天下午2点"},
        ),
    )
    assert "时间格式无法识别" in bad_format


async def test_handle_schedule_appointment_success():
    with patch("routers.wechat.create_appointment_task", new=AsyncMock(return_value=SimpleNamespace(id=5))):
        scheduled = await wechat._handle_schedule_appointment(
            DOCTOR,
            IntentResult(
                intent=Intent.schedule_appointment,
                patient_name="王五",
                extra_data={"appointment_time": "2026-03-15T14:00:00", "notes": "复诊"},
            ),
        )
    assert "已为患者【王五】安排预约" in scheduled
    assert "任务编号：5" in scheduled


async def test_handle_intent_fast_complete_and_task_intents():
    with patch("routers.wechat.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("routers.wechat.update_task_status", new=AsyncMock(return_value=SimpleNamespace(title="紧急记录：王五"))):
        direct = await wechat._handle_intent("完成 7", DOCTOR)
    assert "已标记完成" in direct

    with patch("services.ai.agent.dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.list_tasks))), \
         patch("routers.wechat._handle_list_tasks", new=AsyncMock(return_value="tasks")):
        r1 = await wechat._handle_intent("我的待办", DOCTOR)
    assert r1 == "tasks"

    with patch("services.ai.agent.dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.complete_task, extra_data={"task_id": 3}))), \
         patch("routers.wechat._handle_complete_task", new=AsyncMock(return_value="done")):
        r2 = await wechat._handle_intent("完成任务3", DOCTOR)
    assert r2 == "done"


async def test_handle_intent_schedule_and_delete_patient_routing():
    with patch("services.ai.agent.dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.schedule_appointment, patient_name="赵六", extra_data={"appointment_time": "2026-03-18T09:00:00"}))), \
         patch("routers.wechat._handle_schedule_appointment", new=AsyncMock(return_value="appt")):
        r3 = await wechat._handle_intent("约诊", DOCTOR)
    assert r3 == "appt"

    with patch("services.ai.agent.dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.delete_patient, patient_name="章三", extra_data={"occurrence_index": 2}))), \
         patch("routers.wechat.wd.handle_delete_patient", new=AsyncMock(return_value="deleted")):
        r4 = await wechat._handle_intent("删除第二个患者章三", DOCTOR)
    assert r4 == "deleted"


async def test_handle_intent_notify_control_commands():
    with patch(
        "routers.wechat.set_notify_mode",
        new=AsyncMock(return_value=SimpleNamespace(notify_mode="manual")),
    ):
        out = await wechat._handle_intent("通知模式 手动", DOCTOR)
    assert "通知模式已更新" in out

    with patch(
        "routers.wechat.run_due_task_cycle",
        new=AsyncMock(return_value={"due_count": 2, "eligible_count": 2, "sent_count": 1, "failed_count": 0}),
    ):
        out2 = await wechat._handle_intent("立即发送待办", DOCTOR)
    assert "sent=1" in out2


# ---------------------------------------------------------------------------
# Signature verification tests
# ---------------------------------------------------------------------------


def test_verify_signature_success_and_failure():
    ok = wechat.verify("1", "2", "sig", "echo")
    assert ok.status_code in (200, 403)

    with patch("routers.wechat.check_signature", side_effect=wechat.InvalidSignatureException("bad")):
        resp = wechat.verify("1", "2", "sig", "echo")
    assert resp.status_code == 403

    with patch("routers.wechat.check_signature", return_value=None):
        resp2 = wechat.verify("1", "2", "sig", "echo")
    assert resp2.status_code == 200
    assert resp2.body == b"echo"


def test_verify_wecom_msg_signature_path():
    fake_crypto = SimpleNamespace(check_signature=lambda *_: "echo-decoded")
    with patch(
        "routers.wechat._get_config",
        return_value={
            "token": "tok",
            "app_id": "ww-corp",
            "app_secret": "sec",
            "aes_key": "aes",
            "open_kfid": "",
            "is_kf": True,
        },
    ), patch("routers.wechat.EnterpriseWeChatCrypto", return_value=fake_crypto):
        resp = wechat.verify(
            timestamp="1",
            nonce="2",
            signature="",
            echostr="encrypted-echo",
            msg_signature="msgsig",
        )
    assert resp.status_code == 200
    assert resp.body == b"echo-decoded"


def test_verify_without_params_returns_ok_for_domain_probe():
    resp = wechat.verify()
    assert resp.status_code == 200
    assert resp.body == b"ok"


def test_verify_missing_signature_returns_echo_or_ok():
    resp = wechat.verify(timestamp="1", nonce="2", signature="", msg_signature="", echostr="echo-x")
    assert resp.status_code == 200
    assert resp.body == b"echo-x"


# ---------------------------------------------------------------------------
# _handle_intent_bg tests
# ---------------------------------------------------------------------------


async def test_handle_intent_bg_uses_context_and_fallback():
    clear_pending_record_id(DOCTOR)
    clear_pending_create(DOCTOR)
    with patch("routers.wechat.get_session_lock", return_value=DummyLock()), \
         patch("routers.wechat.hydrate_session_state", new=AsyncMock()), \
         patch("routers.wechat.maybe_compress", new=AsyncMock()), \
         patch("routers.wechat.load_context_message", new=AsyncMock(return_value={"role": "system", "content": "ctx"})), \
         patch("routers.wechat._handle_intent", new=AsyncMock(side_effect=RuntimeError("x"))), \
         patch("routers.wechat.push_turn") as push_turn, \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_intent_bg("hello", DOCTOR)

    push_turn.assert_called_once()
    assert push_turn.call_args.args[2]
    send_msg.assert_awaited_once()


async def test_handle_intent_bg_pending_create_bypasses_llm():
    clear_pending_record_id(DOCTOR)
    set_pending_create(DOCTOR, "章三")
    with patch("routers.wechat.get_session_lock", return_value=DummyLock()), \
         patch("routers.wechat.hydrate_session_state", new=AsyncMock()), \
         patch("routers.wechat._handle_pending_create", new=AsyncMock(return_value="好的，章三已创建（男、17岁）。")) as pending_mock, \
         patch("routers.wechat._handle_intent", new=AsyncMock()) as intent_mock, \
         patch("routers.wechat.push_turn") as push_turn, \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_intent_bg("男，17", DOCTOR)

    pending_mock.assert_awaited_once_with("男，17", DOCTOR)
    intent_mock.assert_not_awaited()
    push_turn.assert_called_once()
    send_msg.assert_awaited_once()


async def test_handle_intent_bg_kf_schedules_customer_prefetch():
    captured = {"scheduled": False}

    async def _fake_prefetch(_doctor_id):
        captured["scheduled"] = True

    def _capture_task(coro):
        return asyncio.get_running_loop().create_task(coro)

    with patch("routers.wechat.get_session_lock", return_value=DummyLock()), \
         patch("routers.wechat.prefetch_customer_profile", side_effect=_fake_prefetch), \
         patch("routers.wechat.asyncio.create_task", side_effect=_capture_task), \
         patch("routers.wechat.maybe_compress", new=AsyncMock()), \
         patch("routers.wechat.load_context_message", new=AsyncMock(return_value=None)), \
         patch("routers.wechat._handle_intent", new=AsyncMock(return_value="ok")), \
         patch("routers.wechat.push_turn"), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()):
        await wechat._handle_intent_bg("hello", DOCTOR, open_kfid="wk-001")
        await asyncio.sleep(0.01)

    assert captured["scheduled"] is True


# ---------------------------------------------------------------------------
# handle_message routing tests
# ---------------------------------------------------------------------------


async def test_handle_message_text_routing_paths():
    clear_pending_create(DOCTOR)
    msg = SimpleNamespace(type="text", source=DOCTOR, content="hello")
    req = DummyRequest(query_params={}, body="<xml/>")

    def _consume_task(coro):
        coro.close()
        return None

    with patch("routers.wechat.parse_message", return_value=msg), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat.hydrate_session_state", new=AsyncMock(return_value=get_session(DOCTOR))), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as create_task:
        resp = await wechat.handle_message(req)
    assert resp.status_code == 200
    assert "正在处理" in resp.body.decode("utf-8")
    assert any(
        "_handle_intent_bg" in str(call.args[0])
        for call in create_task.call_args_list
    )


async def test_handle_message_routes_patient_to_pipeline():
    """Non-doctor senders are routed to the patient pipeline background task."""
    msg = SimpleNamespace(type="text", source="unknown_patient_openid", content="你好")
    req = DummyRequest(query_params={}, body="<xml/>")

    def _consume_task(coro):
        coro.close()
        return None

    with patch("routers.wechat.parse_message", return_value=msg), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat._is_registered_doctor", new=AsyncMock(return_value=False)), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as create_task:
        resp = await wechat.handle_message(req)

    assert resp.status_code == 200
    assert any(
        "_handle_patient_bg" in str(call.args[0])
        for call in create_task.call_args_list
    )


async def test_handle_message_event_click_acks_menu():
    req = DummyRequest(query_params={}, body="<xml/>")
    click = SimpleNamespace(type="event", event="CLICK", key="DOCTOR_QUERY", source=DOCTOR)
    with patch("routers.wechat.parse_message", return_value=click), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat._handle_menu_event", new=AsyncMock(return_value="menu")):
        resp = await wechat.handle_message(req)
    assert "menu" in resp.body.decode("utf-8")


async def test_handle_message_voice_and_image_ack():
    req = DummyRequest(query_params={}, body="<xml/>")

    def _consume_task(coro):
        coro.close()
        return None

    voice = SimpleNamespace(type="voice", source=DOCTOR, media_id="m1")
    with patch("routers.wechat.parse_message", return_value=voice), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task):
        resp2 = await wechat.handle_message(req)
    assert "收到语音" in resp2.body.decode("utf-8")

    image = SimpleNamespace(type="image", source=DOCTOR, media_id="m2")
    with patch("routers.wechat.parse_message", return_value=image), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task):
        resp3 = await wechat.handle_message(req)
    assert "收到图片" in resp3.body.decode("utf-8")


async def test_handle_message_parse_and_decrypt_failure_paths():
    req = DummyRequest(
        query_params={"encrypt_type": "aes", "msg_signature": "m", "timestamp": "t", "nonce": "n"},
        body="<xml/>",
    )
    with patch("routers.wechat.WeChatCrypto", return_value=SimpleNamespace(decrypt_message=lambda *_: (_ for _ in ()).throw(RuntimeError("bad")))):
        resp = await wechat.handle_message(req)
    assert resp.status_code == 200

    with patch("routers.wechat.parse_message", side_effect=RuntimeError("bad parse")):
        resp2 = await wechat.handle_message(DummyRequest(body="<xml/>"))
    assert resp2.status_code == 200


async def test_handle_message_encrypted_payload_without_decrypt_config_acks_success():
    req = DummyRequest(
        query_params={"msg_signature": "m", "timestamp": "t", "nonce": "n"},
        body="<xml><ToUserName><![CDATA[x]]></ToUserName><Encrypt><![CDATA[abc]]></Encrypt></xml>",
    )
    with patch(
        "routers.wechat._get_config",
        return_value={
            "token": "t",
            "app_id": "",
            "app_secret": "",
            "aes_key": "",
            "open_kfid": "",
            "is_kf": True,
        },
    ):
        resp = await wechat.handle_message(req)
    assert resp.status_code == 200
    assert resp.body.decode("utf-8") == "success"


async def test_handle_message_kf_event_passes_token_and_open_kfid_to_sync_task():
    req = DummyRequest(
        body=(
            "<xml>"
            "<Event><![CDATA[kf_msg_or_event]]></Event>"
            "<MsgId><![CDATA[msg-1]]></MsgId>"
            "<CreateTime>5000</CreateTime>"
            "<Token><![CDATA[event-token-1]]></Token>"
            "<OpenKfId><![CDATA[wk-open-kf-1]]></OpenKfId>"
            "</xml>"
        )
    )

    captured = {}

    def _capture_task(coro):
        captured.update(coro.cr_frame.f_locals)
        coro.close()
        return None

    with patch("routers.wechat.asyncio.create_task", side_effect=_capture_task):
        resp = await wechat.handle_message(req)

    assert resp.status_code == 200
    assert captured.get("expected_msgid") == "msg-1"
    assert captured.get("event_create_time") == 5000
    assert captured.get("event_token") == "event-token-1"
    assert captured.get("event_open_kfid") == "wk-open-kf-1"


async def test_setup_menu_status_paths():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.create_menu", new=AsyncMock(return_value={"errcode": 0})):
        ok = await wechat.setup_menu()
    assert ok["status"] == "ok"

    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.create_menu", new=AsyncMock(return_value={"errcode": 1, "errmsg": "x"})):
        err = await wechat.setup_menu()
    assert err["status"] == "error"
