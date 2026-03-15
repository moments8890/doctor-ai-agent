"""
微信入口多输入类型路由端到端测试。

E2E-style multi-input routing tests for WeChat entrypoints.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import channels.wechat.router as wechat


class DummyRequest:
    def __init__(self, query_params=None, body=""):
        self.query_params = query_params or {}
        self._body = body.encode("utf-8")

    async def body(self):
        return self._body


class FakeTextReply:
    def __init__(self, content, message):
        self.content = content
        self.message = message

    def render(self):
        return self.content


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, _url, params, json):
        return _Resp(self.payload)


def _consume_task(coro):
    coro.close()
    return None


async def test_wecom_kf_image_media_routes_to_image_bg():
    data = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "i1",
                "external_userid": "u1",
                "open_kfid": "kf1",
                "send_time": 1000,
                "msgtype": "image",
                "image": {"media_id": "img-mid"},
            }
        ],
    }
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    with patch("routers.wechat._get_config", return_value={"app_id": "ww-corp", "app_secret": "sec"}), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_Client(data)), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_mock, \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as task_mock, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(event_create_time=1000)

    send_mock.assert_awaited_once()
    task_mock.assert_called_once()


async def test_wecom_kf_location_link_weapp_route_to_intent_bg():
    cases = [
        {"msgtype": "location", "location": {"title": "门诊楼"}},
        {"msgtype": "link", "link": {"title": "检查报告", "url": "https://example.com"}},
        {"msgtype": "weapp", "weapp": {"title": "检查小程序", "pagepath": "pages/index"}},
    ]
    for idx, extra in enumerate(cases, start=1):
        data = {
            "errcode": 0,
            "has_more": 0,
            "next_cursor": "c1",
            "msg_list": [
                {
                    "origin": 3,
                    "msgid": f"x{idx}",
                    "external_userid": "u1",
                    "open_kfid": "kf1",
                    "send_time": 1000,
                    **extra,
                }
            ],
        }
        wechat._WECHAT_KF_SYNC_CURSOR = ""
        wechat._WECHAT_KF_CURSOR_LOADED = True
        wechat._WECHAT_KF_SEEN_MSG_IDS.clear()
        with patch("routers.wechat._get_config", return_value={"app_id": "ww-corp", "app_secret": "sec"}), \
             patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
             patch("routers.wechat.httpx.AsyncClient", return_value=_Client(data)), \
             patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_mock, \
             patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as task_mock, \
             patch("routers.wechat._persist_wecom_kf_sync_cursor"):
            await wechat._handle_wecom_kf_event_bg(event_create_time=1000)
        send_mock.assert_not_awaited()
        task_mock.assert_called_once()


async def test_wecom_kf_video_sends_notice_without_intent_dispatch():
    data = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "vd1",
                "external_userid": "u1",
                "open_kfid": "kf1",
                "send_time": 1000,
                "msgtype": "video",
                "video": {"media_id": "vid-mid"},
            }
        ],
    }
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    with patch("routers.wechat._get_config", return_value={"app_id": "ww-corp", "app_secret": "sec"}), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_Client(data)), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_mock, \
         patch("routers.wechat.asyncio.create_task") as task_mock, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(event_create_time=1000)

    send_mock.assert_awaited_once()
    task_mock.assert_not_called()


async def test_wecom_kf_unknown_type_sends_fallback_notice():
    data = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "u1",
                "external_userid": "u1",
                "open_kfid": "kf1",
                "send_time": 1000,
                "msgtype": "mixed",
            }
        ],
    }
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    with patch("routers.wechat._get_config", return_value={"app_id": "ww-corp", "app_secret": "sec"}), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_Client(data)), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_mock, \
         patch("routers.wechat.asyncio.create_task") as task_mock, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(event_create_time=1000)

    send_mock.assert_awaited_once()
    task_mock.assert_not_called()


async def test_wecom_kf_voice_without_media_or_recognition_sends_notice():
    data = {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "v2",
                "external_userid": "u1",
                "open_kfid": "kf1",
                "send_time": 1000,
                "msgtype": "voice",
                "voice": {},
            }
        ],
    }
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()

    with patch("routers.wechat._get_config", return_value={"app_id": "ww-corp", "app_secret": "sec"}), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_Client(data)), \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_mock, \
         patch("routers.wechat.asyncio.create_task") as task_mock, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(event_create_time=1000)

    send_mock.assert_awaited_once()
    task_mock.assert_not_called()


async def test_official_account_video_location_link_supported():
    req = DummyRequest(query_params={}, body="<xml/>")

    video_msg = SimpleNamespace(type="video", source="doc", media_id="m1")
    with patch("routers.wechat.parse_message", return_value=video_msg), \
         patch("routers.wechat.TextReply", FakeTextReply):
        resp = await wechat.handle_message(req)
    assert "收到视频" in resp.body.decode("utf-8")

    location_msg = SimpleNamespace(type="location", source="doc", label="门诊楼", location_x="23.1", location_y="113.3")
    with patch("routers.wechat.parse_message", return_value=location_msg), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as task_mock:
        resp2 = await wechat.handle_message(req)
    assert "收到位置" in resp2.body.decode("utf-8")
    task_mock.assert_called_once()

    link_msg = SimpleNamespace(type="link", source="doc", title="检验报告", url="https://example.com")
    with patch("routers.wechat.parse_message", return_value=link_msg), \
         patch("routers.wechat.TextReply", FakeTextReply), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as task_mock2:
        resp3 = await wechat.handle_message(req)
    assert "收到链接" in resp3.body.decode("utf-8")
    task_mock2.assert_called_once()
