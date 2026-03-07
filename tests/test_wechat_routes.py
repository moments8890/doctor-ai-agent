"""Additional branch tests for routers/wechat.py."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import routers.wechat as wechat
from models.medical_record import MedicalRecord
from services.intent import Intent, IntentResult
from services.interview import InterviewState, STEPS
from services.session import clear_pending_create, get_session, set_pending_create


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


def test_get_config_prefers_wechat_kf_env_aliases():
    with patch.dict(
        "os.environ",
        {
            "WECHAT_KF_TOKEN": "kf-token",
            "WECHAT_KF_CORP_ID": "ww-corp",
            "WECHAT_KF_SECRET": "kf-secret",
            "WECHAT_KF_ENCODING_AES_KEY": "kf-aes",
            "WECHAT_TOKEN": "legacy-token",
            "WECHAT_APP_ID": "legacy-id",
            "WECHAT_APP_SECRET": "legacy-secret",
            "WECHAT_ENCODING_AES_KEY": "legacy-aes",
        },
        clear=False,
    ):
        cfg = wechat._get_config()

    assert cfg["token"] == "kf-token"
    assert cfg["app_id"] == "ww-corp"
    assert cfg["app_secret"] == "kf-secret"
    assert cfg["aes_key"] == "kf-aes"


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


async def test_get_access_token_uses_shared_db_cache_when_local_empty():
    import services.wechat_notify as wn
    wn._token_cache["token"] = ""
    wn._token_cache["expires_at"] = 0

    runtime_token = SimpleNamespace(token_value="shared-token", expires_at=datetime(2099, 1, 1))
    with patch("services.wechat_notify.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("services.wechat_notify.get_runtime_token", new=AsyncMock(return_value=runtime_token)), \
         patch("services.wechat_notify.httpx.AsyncClient") as client_cls:
        token = await wechat._get_access_token("appid", "secret")

    assert token == "shared-token"
    client_cls.assert_not_called()


async def test_get_access_token_persists_shared_db_cache_after_refresh():
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

    mock_upsert = AsyncMock()
    with patch("services.wechat_notify.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("services.wechat_notify.get_runtime_token", new=AsyncMock(return_value=None)), \
         patch("services.wechat_notify.upsert_runtime_token", mock_upsert), \
         patch("services.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        token = await wechat._get_access_token("appid", "secret")

    assert token == "fresh-token"
    mock_upsert.assert_awaited_once()


async def test_get_access_token_uses_wecom_kf_gettoken_for_corp_id():
    import services.wechat_notify as wn
    wn._token_cache["token"] = ""
    wn._token_cache["expires_at"] = 0

    class _Resp:
        def json(self):
            return {"access_token": "kf-token", "expires_in": 7200}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params):
            assert "qyapi.weixin.qq.com/cgi-bin/gettoken" in url
            assert params["corpid"] == "ww-corp-id"
            assert params["corpsecret"] == "corp-secret"
            return _Resp()

    with patch("services.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        token = await wechat._get_access_token("ww-corp-id", "corp-secret")

    assert token == "kf-token"


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


async def test_send_customer_service_msg_kf_requires_open_kfid():
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, json):
            return SimpleNamespace(json=lambda: {"errcode": 0})

    with patch(
        "services.wechat_notify._get_config",
        return_value={
            "token": "tok",
            "app_id": "ww-corp",
            "app_secret": "secret",
            "aes_key": "",
            "open_kfid": "",
            "is_kf": True,
        },
    ), patch("services.wechat_notify._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        with pytest.raises(RuntimeError, match="WECHAT_KF_OPEN_KFID"):
            await wechat._send_customer_service_msg("u1", "hello")


async def test_send_customer_service_msg_kf_payload_includes_open_kfid():
    captured = {}

    class _Resp:
        def json(self):
            return {"errcode": 0, "errmsg": "ok"}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, json):
            captured["payload"] = json
            return _Resp()

    with patch(
        "services.wechat_notify._get_config",
        return_value={
            "token": "tok",
            "app_id": "ww-corp",
            "app_secret": "secret",
            "aes_key": "",
            "open_kfid": "kf-001",
            "is_kf": True,
        },
    ), patch("services.wechat_notify._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        await wechat._send_customer_service_msg("u1", "hello")

    assert captured["payload"]["open_kfid"] == "kf-001"


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

    # Interview completion now routes through confirmation gate — returns draft preview
    assert "草稿" in result or "确认" in result
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
    assert "章三已建档" in out

    async with session_factory() as s2:
        from db.crud import get_all_patients
        after = await get_all_patients(s2, DOCTOR)
    assert len([p for p in after if p.name == "章三"]) == 1


async def test_handle_intent_add_record_asks_for_name_without_session():
    with patch(
        "routers.wechat.agent_dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
    ):
        msg = await wechat._handle_intent("发烧一天", DOCTOR)
    assert "叫什么名字" in msg


async def test_handle_intent_add_record_name_token_routes_to_lookup():
    with patch(
        "routers.wechat.agent_dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
    ), patch("routers.wechat._handle_name_lookup", new=AsyncMock(return_value="lookup-name")) as lookup_mock:
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
             "routers.wechat.agent_dispatch",
             new=AsyncMock(return_value=IntentResult(intent=Intent.add_record, patient_name=None)),
         ), \
         patch("routers.wechat._handle_add_record", new=AsyncMock(return_value="saved")) as add_mock:
        msg = await wechat._handle_intent("头疼", DOCTOR)

    assert msg == "saved"
    add_mock.assert_awaited_once()
    assert get_session(DOCTOR).current_patient_name == "张三"


async def test_handle_intent_unknown_no_longer_routes_to_name_lookup():
    with patch(
        "routers.wechat.agent_dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply=None)),
    ), patch("routers.wechat._handle_name_lookup", new=AsyncMock(return_value="lookup")):
        out = await wechat._handle_intent("张三", DOCTOR)
    assert "请直接描述病历" in out


async def test_handle_intent_unknown_explicit_name_routes_to_lookup():
    with patch(
        "routers.wechat.agent_dispatch",
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
        "routers.wechat.agent_dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply=None)),
    ), patch("routers.wechat._handle_add_record", new=AsyncMock(return_value="saved-brief")) as add_mock:
        out = await wechat._handle_intent("我又有偏头痛", DOCTOR)
    assert out == "saved-brief"
    add_mock.assert_awaited_once()


async def test_handle_intent_unknown_greeting_not_routed_as_name():
    with patch(
        "routers.wechat.agent_dispatch",
        new=AsyncMock(return_value=IntentResult(intent=Intent.unknown, chat_reply=None)),
    ), patch("routers.wechat._handle_name_lookup", new=AsyncMock(return_value="lookup")) as lookup_mock:
        out = await wechat._handle_intent("你好", DOCTOR)

    assert "您好" in out or "请直接描述病历" in out
    lookup_mock.assert_not_called()


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

    with patch("routers.wechat.agent_dispatch", new=AsyncMock(return_value=IntentResult(intent=Intent.delete_patient, patient_name="章三", extra_data={"occurrence_index": 2}))), \
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


async def test_handle_intent_bg_pending_create_bypasses_llm():
    set_pending_create(DOCTOR, "章三")
    with patch("routers.wechat.get_session_lock", return_value=DummyLock()), \
         patch("routers.wechat._handle_pending_create", new=AsyncMock(return_value="好的，章三已建档（男、17岁）。")) as pending_mock, \
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
        # Run enrichment task immediately for deterministic assertion.
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


async def test_voice_and_image_bg_error_paths():
    with patch("routers.wechat._get_access_token", new=AsyncMock(side_effect=RuntimeError("no token"))), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_voice_bg("m1", DOCTOR)
    send_msg.assert_awaited_once()
    voice_msg = send_msg.await_args.args[1]
    assert "语音识别失败" in voice_msg
    assert "no token" not in voice_msg

    with patch("routers.wechat._get_access_token", new=AsyncMock(side_effect=RuntimeError("no token"))), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg2:
        await wechat._handle_image_bg("m2", DOCTOR)
    send_msg2.assert_awaited_once()
    image_msg = send_msg2.await_args.args[1]
    assert "图片识别失败" in image_msg
    assert "no token" not in image_msg


async def test_pdf_file_bg_success_routes_to_intent():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_voice", new=AsyncMock(return_value=b"%PDF-1.7")), \
         patch("routers.wechat.extract_text_from_pdf", return_value="章三 偏头痛 3天"), \
         patch("routers.wechat._handle_intent_bg", new=AsyncMock()) as intent_bg, \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_pdf_file_bg("m-pdf", "case.pdf", DOCTOR, open_kfid="kf1")
    intent_bg.assert_awaited_once()
    send_msg.assert_not_awaited()


async def test_file_bg_detects_pdf_by_header_without_pdf_extension():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_voice", new=AsyncMock(return_value=b"%PDF-1.7\n...")), \
         patch("routers.wechat._handle_pdf_file_bg", new=AsyncMock()) as pdf_bg:
        await wechat._handle_file_bg("m-file", "文件", DOCTOR, open_kfid="kf1")
    pdf_bg.assert_awaited_once()


async def test_file_bg_non_pdf_sends_notice():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_voice", new=AsyncMock(return_value=b"PK\x03\x04...")), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_file_bg("m-file", "报告.docx", DOCTOR, open_kfid="kf1")
    send_msg.assert_awaited_once()


async def test_file_bg_download_failure_sends_generic_error():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_voice", new=AsyncMock(side_effect=RuntimeError("network secret"))), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_file_bg("m-file", "报告.docx", DOCTOR, open_kfid="kf1")
    send_msg.assert_awaited_once()
    msg = send_msg.await_args.args[1]
    assert "文件下载失败" in msg
    assert "network secret" not in msg


async def test_pdf_file_bg_failure_sends_error_notice():
    with patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.download_voice", new=AsyncMock(return_value=b"%PDF-1.7")), \
         patch("routers.wechat.extract_text_from_pdf", side_effect=RuntimeError("pdftotext failed")), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_msg:
        await wechat._handle_pdf_file_bg("m-pdf", "case.pdf", DOCTOR, open_kfid="kf1")
    send_msg.assert_awaited_once()
    pdf_msg = send_msg.await_args.args[1]
    assert "PDF解析失败" in pdf_msg
    assert "pdftotext failed" not in pdf_msg


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


async def test_handle_message_rejects_unknown_sender():
    """Non-doctor senders must receive the patient-facing reply, not the agent."""
    msg = SimpleNamespace(type="text", source="unknown_patient_openid", content="你好")
    req = DummyRequest(query_params={}, body="<xml/>")
    with patch("routers.wechat.parse_message", return_value=msg), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat._is_registered_doctor", new=AsyncMock(return_value=False)):
        resp = await wechat.handle_message(req)
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert "此服务专供医生使用" in body


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


# ---------------------------------------------------------------------------
# WeCom KF sync selection paths
# ---------------------------------------------------------------------------


async def test_wecom_kf_sync_paginates_and_picks_nearest_event_message():
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    page_1 = {
        "errcode": 0,
        "has_more": 1,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "old-1",
                "external_userid": "u1",
                "open_kfid": "kf1",
                "send_time": 1000,
                "msgtype": "text",
                "text": {"content": "旧消息"},
            }
        ],
    }
    page_2 = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c2",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "new-1",
                "external_userid": "u1",
                "open_kfid": "kf1",
                "send_time": 5001,
                "msgtype": "text",
                "text": {"content": "我是张三"},
            }
        ],
    }

    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _Client:
        def __init__(self):
            self._queue = [page_1, page_2]
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, params, json):
            self.calls.append({"params": params, "json": json})
            return _Resp(self._queue.pop(0))

    captured = {}

    def _consume_task(coro):
        frame = getattr(coro, "cr_frame", None)
        local_vars = dict(frame.f_locals) if frame is not None else {}
        if "text" in local_vars and "doctor_id" in local_vars:
            captured["locals"] = local_vars
        coro.close()
        return None

    with patch(
        "routers.wechat._get_config",
        return_value={"app_id": "ww-corp", "app_secret": "sec"},
    ), patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_Client()), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task), \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5002)

    assert wechat._WECHAT_KF_SYNC_CURSOR == "c2"
    assert captured["locals"]["text"] == "我是张三"
    assert captured["locals"]["doctor_id"] == "u1"
    assert captured["locals"]["open_kfid"] == "kf1"


async def test_wecom_kf_sync_includes_event_token_and_open_kfid_in_payload():
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    data = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "new-1",
                "external_userid": "u1",
                "open_kfid": "kf1",
                "send_time": 5001,
                "msgtype": "text",
                "text": {"content": "我是张三"},
            }
        ],
    }

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return data

    class _Client:
        def __init__(self):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, params, json):
            self.calls.append({"params": params, "json": dict(json)})
            return _Resp()

    client = _Client()

    def _consume_task(coro):
        coro.close()
        return None

    with patch(
        "routers.wechat._get_config",
        return_value={"app_id": "ww-corp", "app_secret": "sec"},
    ), patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=client), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task), \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(
            expected_msgid="",
            event_create_time=5000,
            event_token="event-token-1",
            event_open_kfid="wk-open-kf-1",
        )

    assert client.calls, "sync_msg should be called at least once"
    request_json = client.calls[0]["json"]
    assert request_json.get("token") == "event-token-1"
    assert request_json.get("open_kfid") == "wk-open-kf-1"


async def test_wecom_kf_sync_skips_stale_batch_when_event_time_far_away():
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    data = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "old-2",
                "external_userid": "u2",
                "open_kfid": "kf2",
                "send_time": 1000,
                "msgtype": "text",
                "text": {"content": "你好"},
            }
        ],
    }

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return data

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, params, json):
            return _Resp()

    with patch(
        "routers.wechat._get_config",
        return_value={"app_id": "ww-corp", "app_secret": "sec"},
    ), patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_Client()), \
         patch("routers.wechat.asyncio.create_task") as create_task, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5000)

    assert all(
        getattr(getattr(call.args[0], "cr_code", None), "co_name", "") != "_handle_intent_bg"
        for call in create_task.call_args_list
    )


async def test_wecom_kf_sync_pdf_file_message_sends_notice_and_starts_pdf_bg():
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    data = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "file-1",
                "external_userid": "u-file",
                "open_kfid": "kf-file",
                "send_time": 5000,
                "msgtype": "file",
                "file": {"filename": "case.pdf", "media_id": "m-pdf-1"},
            }
        ],
    }

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return data

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, params, json):
            return _Resp()

    def _consume_task(coro):
        coro.close()
        return None

    with patch(
        "routers.wechat._get_config",
        return_value={"app_id": "ww-corp", "app_secret": "sec"},
    ), patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_Client()), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as create_task, \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_mock, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5000)

    assert any(
        getattr(getattr(call.args[0], "cr_code", None), "co_name", "") == "_handle_file_bg"
        for call in create_task.call_args_list
    )
    send_mock.assert_awaited_once()


async def test_wecom_kf_sync_non_pdf_file_message_sends_notice_only():
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    data = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "file-2",
                "external_userid": "u-file",
                "open_kfid": "kf-file",
                "send_time": 5000,
                "msgtype": "file",
                "file": {"filename": "case.docx", "media_id": "m-docx-1"},
            }
        ],
    }

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return data

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, params, json):
            return _Resp()

    def _consume_task(coro):
        coro.close()
        return None

    with patch(
        "routers.wechat._get_config",
        return_value={"app_id": "ww-corp", "app_secret": "sec"},
    ), patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_Client()), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as create_task, \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_mock, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5000)

    assert any(
        getattr(getattr(call.args[0], "cr_code", None), "co_name", "") == "_handle_file_bg"
        for call in create_task.call_args_list
    )
    send_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# structured_fields path in _handle_add_record
# ---------------------------------------------------------------------------


async def test_handle_add_record_uses_structured_fields(session_factory):
    """When structured_fields is set, structure_medical_record should NOT be called.
    Normal records now go through the confirmation gate — returns a draft preview."""
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
    # Confirmation gate: reply is draft preview, not the original chat_reply
    assert "草稿" in reply or "确认" in reply
    assert "张三" in reply


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
    """Normal records go through the confirmation gate — returns draft preview, not chat_reply."""
    intent = IntentResult(
        intent=Intent.add_record,
        patient_name="李明",
        structured_fields={"chief_complaint": "发烧三天"},
        chat_reply="李明发烧三天，退烧药已记录。",
    )
    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_add_record("李明发烧三天", DOCTOR, intent)
    assert "草稿" in reply or "确认" in reply
    assert "李明" in reply


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


# ---------------------------------------------------------------------------
# Confirmation gate: _confirm_pending_record and _handle_pending_record_reply
# ---------------------------------------------------------------------------

async def test_handle_pending_record_reply_confirm(session_factory):
    """Replying 确认 saves the pending record and clears session state."""
    from services.session import set_pending_record_id, get_session as _gs
    import json as _json
    from models.medical_record import MedicalRecord

    fake_record = MedicalRecord(chief_complaint="头痛两天", diagnosis="偏头痛")
    from db.crud import create_pending_record as _create_pr

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

    # Patch the background task functions individually to avoid breaking SQLAlchemy internals
    with patch("routers.wechat.AsyncSessionLocal", session_factory), \
         patch("routers.wechat.audit", new=AsyncMock()), \
         patch("routers.wechat.create_follow_up_task", new=AsyncMock()), \
         patch("routers.wechat.wd._bg_auto_learn", new=AsyncMock()):
        reply = await wechat._handle_pending_record_reply("确认", DOCTOR, sess)

    assert "✅" in reply or "已保存" in reply
    assert _gs(DOCTOR).pending_record_id is None


async def test_handle_pending_record_reply_cancel(session_factory):
    """Replying 取消 abandons the pending record and clears session state."""
    from services.session import set_pending_record_id, get_session as _gs
    import json as _json
    from models.medical_record import MedicalRecord
    from db.crud import create_pending_record as _create_pr

    fake_record = MedicalRecord(chief_complaint="腹痛")
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

    assert "放弃" in reply or "取消" in reply
    assert _gs(DOCTOR).pending_record_id is None


async def test_handle_pending_record_reply_expired_draft(session_factory):
    """Replying 确认 when draft doesn't exist returns error and clears state."""
    from services.session import set_pending_record_id, get_session as _gs

    set_pending_record_id(DOCTOR, "nonexistentdraft")
    sess = _gs(DOCTOR)

    with patch("routers.wechat.AsyncSessionLocal", session_factory):
        reply = await wechat._handle_pending_record_reply("确认", DOCTOR, sess)

    assert "过期" in reply or "不存在" in reply
    assert _gs(DOCTOR).pending_record_id is None
