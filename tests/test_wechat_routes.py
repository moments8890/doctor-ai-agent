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
    wechat._token_cache["token"] = "cached-token"
    wechat._token_cache["expires_at"] = 9999999999
    with patch("routers.wechat.httpx.AsyncClient") as client_cls:
        token = await wechat._get_access_token("appid", "secret")
    assert token == "cached-token"
    client_cls.assert_not_called()


async def test_get_access_token_fetches_and_updates_cache():
    wechat._token_cache["token"] = ""
    wechat._token_cache["expires_at"] = 0

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

    with patch("routers.wechat.httpx.AsyncClient", return_value=_Client()):
        token = await wechat._get_access_token("appid", "secret")

    assert token == "fresh-token"
    assert wechat._token_cache["token"] == "fresh-token"
    assert wechat._token_cache["expires_at"] > 0


async def test_send_customer_service_msg_swallow_exception():
    with patch("routers.wechat._get_access_token", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await wechat._send_customer_service_msg("u1", "content")


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
    assert "结束" in result
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

    assert "问诊完成" in result
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
    assert "未找到患者" in miss
    assert get_session(DOCTOR).pending_create_name == "赵六"


async def test_pending_create_cancel_and_create(session_factory):
    set_pending_create(DOCTOR, "陈明")
    cancelled = await wechat._handle_pending_create("取消", DOCTOR)
    assert "已取消" in cancelled
    assert get_session(DOCTOR).pending_create_name is None

    set_pending_create(DOCTOR, "陈明")
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        created = await wechat._handle_pending_create("男，30岁", DOCTOR)
    assert "建档" in created
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
    assert "处理失败" in push_turn.call_args.args[2]
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
