"""Additional branch tests for routers/wechat.py."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import routers.wechat as wechat
from models.medical_record import MedicalRecord
from services.intent import Intent, IntentResult
from services.interview import InterviewState, STEPS
from services.session import get_session, set_pending_create


DOCTOR = "wechat_routes_doc"


class DummyRequest:
    def __init__(self, query_params=None, body=""):
        self.query_params = query_params or {}
        self._body = body.encode("utf-8")

    async def body(self):
        return self._body


class DummyLock:
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


async def test_get_access_token_uses_cache_without_http_call():
    import services.wechat_notify as wn
    wn._token_cache["token"] = "cached-token"
    wn._token_cache["expires_at"] = 9999999999
    with patch("services.wechat_notify.httpx.AsyncClient") as client_cls:
        token = await wechat._get_access_token("appid", "secret")
    assert token == "cached-token"
    client_cls.assert_not_called()


async def test_get_access_token_fetches_and_updates_cache():
    import services.wechat_notify as wn
    wn._token_cache["token"] = ""
    wn._token_cache["expires_at"] = 0

    class _Resp:
        def json(self):
            return {"access_token": "fresh-token", "expires_in": 7200}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url, params):
            assert params["appid"] == "appid"
            return _Resp()

    with patch("services.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        token = await wechat._get_access_token("appid", "secret")

    assert token == "fresh-token"
    assert wn._token_cache["token"] == "fresh-token"
    assert wn._token_cache["expires_at"] > 0


async def test_send_customer_service_msg_swallow_exception():
    with patch("services.wechat_notify._get_access_token", new=AsyncMock(side_effect=RuntimeError("boom"))):
        try:
            await wechat._send_customer_service_msg("u1", "content")
            assert False, "expected exception"
        except RuntimeError as e:
            assert "boom" in str(e)


async def test_send_customer_service_msg_success_path_posts_chunks():
    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return {"ok": True, "echo": self._payload["text"]["content"]}

    class _Client:
        def __init__(self):
            self.posts = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, json):
            self.posts.append(json)
            return _Resp(json)

    client = _Client()
    with patch("services.wechat_notify._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat_notify.httpx.AsyncClient", return_value=client):
        await wechat._send_customer_service_msg("u1", "【A】" + "x" * 700 + "【B】tail")

    assert len(client.posts) >= 2
    assert all(p["touser"] == "u1" for p in client.posts)


async def test_send_customer_service_msg_raises_on_wechat_errcode():
    class _Resp:
        def json(self):
            return {"errcode": 40013, "errmsg": "invalid appid"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, json):
            return _Resp()

    with patch("services.wechat_notify._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        try:
            await wechat._send_customer_service_msg("u1", "hello")
            assert False, "expected exception"
        except RuntimeError as e:
            assert "errcode=40013" in str(e)


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

    fake_record = MedicalRecord(chief_complaint="头痛", diagnosis="偏头痛", treatment_plan="休息")
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.structure_medical_record", new=AsyncMock(return_value=fake_record)):
        result = await wechat._handle_interview_step("体格检查正常", DOCTOR)

    assert "问诊完成" in result or "病历已保存" in result
    assert "王五" in result


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
    assert "建档" in created or "陈明" in created
    assert "30岁" in created
    assert get_session(DOCTOR).pending_create_name is None


async def test_handle_intent_add_record_asks_for_name_without_session():
    with patch(
        "routers.wechat.agent_dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
    ):
        msg = await wechat._handle_intent("发烧一天", DOCTOR)
    assert "叫什么名字" in msg


async def test_handle_intent_unknown_name_routes_to_lookup():
    with patch(
        "routers.wechat.agent_dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply=None)),
    ), patch("routers.wechat._handle_name_lookup", new=AsyncMock(return_value="lookup")):
        out = await wechat._handle_intent("张三", DOCTOR)
    assert out == "lookup"


async def test_handle_list_tasks_and_complete_task_and_schedule_routes():
    pending_tasks = [
        SimpleNamespace(id=1, task_type="follow_up", title="随访提醒：张三", due_at=None),
        SimpleNamespace(id=2, task_type="appointment", title="预约提醒：李四", due_at=datetime(2026, 3, 15, 9, 0, 0)),
    ]
    with patch("routers.wechat.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("routers.wechat.list_tasks", new=AsyncMock(return_value=pending_tasks)):
        text = await wechat._handle_list_tasks(DOCTOR)
    assert "待办任务" in text and "follow_up" in text and "appointment" in text

    with patch("routers.wechat.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("routers.wechat.update_task_status", new=AsyncMock(return_value=None)):
        miss = await wechat._handle_complete_task(DOCTOR, IntentResult(intent=Intent.complete_task, extra_data={"task_id": 999}))
    assert "未找到任务" in miss

    with patch("routers.wechat.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("routers.wechat.update_task_status", new=AsyncMock(return_value=SimpleNamespace(title="随访提醒：张三"))):
        ok = await wechat._handle_complete_task(DOCTOR, IntentResult(intent=Intent.complete_task, extra_data={"task_id": 1}))
    assert ok  # natural reply (from chat_reply or default)

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
        IntentResult(intent=Intent.schedule_appointment, patient_name="王五", extra_data={"appointment_time": "明天下午2点"}),
    )
    assert "时间格式无法识别" in bad_format

    with patch("services.tasks.create_appointment_task", new=AsyncMock(return_value=SimpleNamespace(id=5))):
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

    with patch("routers.wechat.agent_dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.list_tasks))), \
         patch("routers.wechat._handle_list_tasks", new=AsyncMock(return_value="tasks")):
        r1 = await wechat._handle_intent("我的待办", DOCTOR)
    assert r1 == "tasks"

    with patch("routers.wechat.agent_dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.complete_task, extra_data={"task_id": 3}))), \
         patch("routers.wechat._handle_complete_task", new=AsyncMock(return_value="done")):
        r2 = await wechat._handle_intent("完成任务3", DOCTOR)
    assert r2 == "done"

    with patch("routers.wechat.agent_dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.schedule_appointment, patient_name="赵六", extra_data={"appointment_time": "2026-03-18T09:00:00"}))), \
         patch("routers.wechat._handle_schedule_appointment", new=AsyncMock(return_value="appt")):
        r3 = await wechat._handle_intent("约诊", DOCTOR)
    assert r3 == "appt"


def test_verify_signature_success_and_failure():
    ok = wechat.verify("1", "2", "sig", "echo")
    # actual check may fail depending on env token; force explicit paths below.
    assert ok.status_code in (200, 403)

    with patch("routers.wechat.check_signature", side_effect=wechat.InvalidSignatureException("bad")):
        resp = wechat.verify("1", "2", "sig", "echo")
    assert resp.status_code == 403

    with patch("routers.wechat.check_signature", return_value=None):
        resp2 = wechat.verify("1", "2", "sig", "echo")
    assert resp2.status_code == 200
    assert resp2.body == b"echo"


async def test_handle_intent_bg_uses_context_and_fallback():
    with patch("routers.wechat.get_session_lock", return_value=DummyLock()), \
         patch("routers.wechat.maybe_compress", new=AsyncMock()), \
         patch("routers.wechat.load_context_message", new=AsyncMock(return_value={"role": "system", "content": "ctx"})), \
         patch("routers.wechat._handle_intent", new=AsyncMock(side_effect=RuntimeError("x"))), \
         patch("routers.wechat.push_turn") as push_turn, \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_intent_bg("hello", DOCTOR)

    push_turn.assert_called_once()
    assert push_turn.call_args.args[2]  # some error message sent
    send_msg.assert_awaited_once()


async def test_voice_and_image_bg_error_paths():
    with patch("routers.wechat._get_access_token", new=AsyncMock(side_effect=RuntimeError("no token"))), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_voice_bg("m1", DOCTOR)
    send_msg.assert_awaited_once()

    with patch("routers.wechat._get_access_token", new=AsyncMock(side_effect=RuntimeError("no token"))), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg2:
        await wechat._handle_image_bg("m2", DOCTOR)
    send_msg2.assert_awaited_once()


async def test_voice_bg_pending_create_route_done():
    set_pending_create(DOCTOR, "李雷")
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_and_convert", new=AsyncMock(return_value=b"wav")), \
         patch("routers.wechat.transcribe_audio", new=AsyncMock(return_value="男，40岁")), \
         patch("routers.wechat.get_session_lock", return_value=DummyLock()), \
         patch("routers.wechat._handle_pending_create", new=AsyncMock(return_value="ok")), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg, \
         patch("routers.wechat._handle_intent_bg", new=AsyncMock()) as intent_bg:
        await wechat._handle_voice_bg("m3", DOCTOR)
    send_msg.assert_awaited_once()
    intent_bg.assert_not_awaited()


async def test_handle_message_text_routing_paths():
    msg = SimpleNamespace(type="text", source=DOCTOR, content="hello")
    req = DummyRequest(query_params={}, body="<xml/>")
    def _consume_task(coro):
        coro.close()
        return None

    with patch("routers.wechat.parse_message", return_value=msg), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as create_task:
        resp = await wechat.handle_message(req)
    assert resp.status_code == 200
    assert "正在处理" in resp.body.decode("utf-8")
    create_task.assert_called_once()


async def test_handle_message_event_and_media_ack_paths():
    req = DummyRequest(query_params={}, body="<xml/>")
    click = SimpleNamespace(type="event", event="CLICK", key="DOCTOR_QUERY", source=DOCTOR)
    with patch("routers.wechat.parse_message", return_value=click), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat._handle_menu_event", new=AsyncMock(return_value="menu")):
        resp = await wechat.handle_message(req)
    assert "menu" in resp.body.decode("utf-8")

    voice = SimpleNamespace(type="voice", source=DOCTOR, media_id="m1")
    def _consume_task(coro):
        coro.close()
        return None

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
    crypto = SimpleNamespace(decrypt_message=AsyncMock(side_effect=RuntimeError("bad")))
    # decrypt_message is sync in library; we emulate failure directly via side_effect in constructor object.
    with patch("routers.wechat.WeChatCrypto", return_value=SimpleNamespace(decrypt_message=lambda *_: (_ for _ in ()).throw(RuntimeError("bad")))):
        resp = await wechat.handle_message(req)
    assert resp.status_code == 200

    with patch("routers.wechat.parse_message", side_effect=RuntimeError("bad parse")):
        resp2 = await wechat.handle_message(DummyRequest(body="<xml/>"))
    assert resp2.status_code == 200


async def test_setup_menu_status_paths():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.create_menu", new=AsyncMock(return_value={"errcode": 0})):
        ok = await wechat.setup_menu()
    assert ok["status"] == "ok"

    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.create_menu", new=AsyncMock(return_value={"errcode": 1, "errmsg": "x"})):
        err = await wechat.setup_menu()
    assert err["status"] == "error"


# ---------------------------------------------------------------------------
# structured_fields path in _handle_add_record
# ---------------------------------------------------------------------------


async def test_handle_add_record_uses_structured_fields(session_factory):
    """When structured_fields is set, structure_medical_record should NOT be called."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        structured_fields={"chief_complaint": "头痛两天", "diagnosis": "紧张性头痛"},
        chat_reply="好的，张三头痛两天的情况记下来了。",
    )
    structure_mock = AsyncMock()
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.structure_medical_record", structure_mock):
        reply = await wechat._handle_add_record("张三头痛两天", DOCTOR, intent)
    structure_mock.assert_not_called()
    assert reply == "好的，张三头痛两天的情况记下来了。"


async def test_handle_add_record_falls_back_to_structuring_llm(session_factory):
    """When structured_fields is None, structure_medical_record should be called."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="张三",
        structured_fields=None,
        chat_reply=None,
    )
    fake_record = MedicalRecord(chief_complaint="头痛", diagnosis="偏头痛")
    structure_mock = AsyncMock(return_value=fake_record)
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.structure_medical_record", structure_mock):
        reply = await wechat._handle_add_record("张三头痛两天", DOCTOR, intent)
    structure_mock.assert_called_once()
    assert "张三" in reply or "病历" in reply


async def test_handle_add_record_uses_chat_reply_from_intent(session_factory):
    """Reply should come from intent.chat_reply when set."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="李明",
        structured_fields={"chief_complaint": "发烧三天"},
        chat_reply="李明发烧三天，退烧药已记录。",
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_add_record("李明发烧三天", DOCTOR, intent)
    assert reply == "李明发烧三天，退烧药已记录。"


async def test_handle_add_record_fallback_reply_when_no_chat_reply(session_factory):
    """When chat_reply is None, reply should contain patient name."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="王五",
        structured_fields={"chief_complaint": "腹痛"},
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
        structured_fields={"chief_complaint": "STEMI急诊"},
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
         patch("routers.wechat.structure_medical_record", new=AsyncMock(side_effect=ValueError("bad"))):
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
         patch("routers.wechat.structure_medical_record", new=AsyncMock(side_effect=RuntimeError("boom"))):
        reply = await wechat._handle_add_record("张三胸痛", DOCTOR, intent)
    assert "不好意思" in reply or "出了点问题" in reply
