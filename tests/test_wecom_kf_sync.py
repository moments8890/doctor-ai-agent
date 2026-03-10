"""企业微信客服（WeCom KF）消息同步单元测试：覆盖分页拉取、事件令牌传递、过期批次跳过及文件消息处理。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import routers.wechat as wechat


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _reset_kf_state():
    """Reset module-level WeCom KF cursor state before each test."""
    wechat._WECHAT_KF_SYNC_CURSOR = ""
    wechat._WECHAT_KF_CURSOR_LOADED = True
    wechat._WECHAT_KF_SEEN_MSG_IDS.clear()


def _make_simple_resp(data):
    """Return a minimal HTTP response stub that yields *data* from .json()."""
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return data

    return _Resp()


def _make_recording_client(pages):
    """Return an httpx.AsyncClient stub that serves *pages* in order and records calls."""
    class _Client:
        def __init__(self):
            self._queue = list(pages)
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, _url, params, json):
            self.calls.append({"params": params, "json": dict(json)})
            return _make_simple_resp(self._queue.pop(0))

    return _Client()


def _consume_task(coro):
    """Discard a coroutine task without executing it."""
    coro.close()
    return None


_KF_CONFIG_PATCH = {
    "app_id": "ww-corp",
    "app_secret": "sec",
}


# ---------------------------------------------------------------------------
# Pagination and message-selection tests
# ---------------------------------------------------------------------------


def _make_text_msg_page(msgid, send_time, content, has_more=0, next_cursor="c1"):
    """Build a synthetic WeCom KF API response page with a single text message."""
    return {
        "errcode": 0,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "msg_list": [
            {
                "origin": 3,
                "msgid": msgid,
                "external_userid": "u1",
                "open_kfid": "kf1",
                "send_time": send_time,
                "msgtype": "text",
                "text": {"content": content},
            }
        ],
    }


def _capturing_task(captured):
    """Return a task factory that captures locals from intent_bg coroutines."""
    def _handler(coro):
        frame = getattr(coro, "cr_frame", None)
        local_vars = dict(frame.f_locals) if frame is not None else {}
        if "text" in local_vars and "doctor_id" in local_vars:
            captured["locals"] = local_vars
        coro.close()
        return None
    return _handler


async def test_wecom_kf_sync_paginates_and_picks_nearest_event_message():
    _reset_kf_state()
    page_1 = _make_text_msg_page("old-1", send_time=1000, content="旧消息", has_more=1, next_cursor="c1")
    page_2 = _make_text_msg_page("new-1", send_time=5001, content="我是张三", has_more=0, next_cursor="c2")

    captured = {}
    client = _make_recording_client([page_1, page_2])
    with patch("routers.wechat._get_config", return_value=_KF_CONFIG_PATCH), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=client), \
         patch("routers.wechat.asyncio.create_task", side_effect=_capturing_task(captured)), \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5002)

    assert wechat._WECHAT_KF_SYNC_CURSOR == "c2"
    assert captured["locals"]["text"] == "我是张三"
    assert captured["locals"]["doctor_id"] == "u1"
    assert captured["locals"]["open_kfid"] == "kf1"


async def test_wecom_kf_sync_includes_event_token_and_open_kfid_in_payload():
    _reset_kf_state()
    data = _make_text_msg_page("new-1", send_time=5001, content="我是张三")
    client = _make_recording_client([data])
    with patch("routers.wechat._get_config", return_value=_KF_CONFIG_PATCH), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
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
    _reset_kf_state()
    data = _make_text_msg_page("old-2", send_time=1000, content="你好")

    with patch("routers.wechat._get_config", return_value=_KF_CONFIG_PATCH), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_make_recording_client([data])), \
         patch("routers.wechat.asyncio.create_task") as create_task, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5000)

    assert all(
        getattr(getattr(call.args[0], "cr_code", None), "co_name", "") != "_handle_intent_bg"
        for call in create_task.call_args_list
    )


# ---------------------------------------------------------------------------
# File message (PDF and non-PDF) routing tests
# ---------------------------------------------------------------------------


def _make_file_msg_data(filename, media_id, send_time=5000):
    """Build a synthetic WeCom KF API response containing a single file message."""
    return {
        "errcode": 0,
        "has_more": 0,
        "next_cursor": "c1",
        "msg_list": [
            {
                "origin": 3,
                "msgid": "file-1",
                "external_userid": "u-file",
                "open_kfid": "kf-file",
                "send_time": send_time,
                "msgtype": "file",
                "file": {"filename": filename, "media_id": media_id},
            }
        ],
    }


async def test_wecom_kf_sync_pdf_file_message_sends_notice_and_starts_pdf_bg():
    _reset_kf_state()

    data = _make_file_msg_data("case.pdf", "m-pdf-1")

    with patch("routers.wechat._get_config", return_value=_KF_CONFIG_PATCH), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_make_recording_client([data])), \
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
    _reset_kf_state()

    data = _make_file_msg_data("case.docx", "m-docx-1")

    with patch("routers.wechat._get_config", return_value=_KF_CONFIG_PATCH), \
         patch("routers.wechat._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("routers.wechat.httpx.AsyncClient", return_value=_make_recording_client([data])), \
         patch("routers.wechat.asyncio.create_task", side_effect=_consume_task) as create_task, \
         patch("routers.wechat._send_customer_service_msg", new=AsyncMock()) as send_mock, \
         patch("routers.wechat._persist_wecom_kf_sync_cursor"):
        await wechat._handle_wecom_kf_event_bg(expected_msgid="", event_create_time=5000)

    assert any(
        getattr(getattr(call.args[0], "cr_code", None), "co_name", "") == "_handle_file_bg"
        for call in create_task.call_args_list
    )
    send_mock.assert_awaited_once()
