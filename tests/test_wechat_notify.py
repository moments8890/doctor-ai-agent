"""微信通知服务单元测试：覆盖配置读取、令牌获取缓存策略及客服消息发送的各种路径。"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import routers.wechat as wechat


class _SessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Access token caching and refresh tests
# ---------------------------------------------------------------------------


async def test_get_access_token_uses_cache_without_http_call():
    import services.wechat.wechat_notify as wn
    wn._token_cache["token"] = "cached-token"
    wn._token_cache["expires_at"] = 9999999999
    with patch("services.wechat.wechat_notify.httpx.AsyncClient") as client_cls:
        token = await wechat._get_access_token("appid", "secret")
    assert token == "cached-token"
    client_cls.assert_not_called()


async def test_get_access_token_fetches_and_updates_cache():
    import services.wechat.wechat_notify as wn
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

    with patch("services.wechat.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        token = await wechat._get_access_token("appid", "secret")

    assert token == "fresh-token"
    assert wn._token_cache["token"] == "fresh-token"
    assert wn._token_cache["expires_at"] > 0


async def test_get_access_token_uses_shared_db_cache_when_local_empty():
    import services.wechat.wechat_notify as wn
    wn._token_cache["token"] = ""
    wn._token_cache["expires_at"] = 0

    runtime_token = SimpleNamespace(token_value="shared-token", expires_at=datetime(2099, 1, 1))
    with patch("services.wechat.wechat_notify.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("services.wechat.wechat_notify.get_runtime_token", new=AsyncMock(return_value=runtime_token)), \
         patch("services.wechat.wechat_notify.httpx.AsyncClient") as client_cls:
        token = await wechat._get_access_token("appid", "secret")

    assert token == "shared-token"
    client_cls.assert_not_called()


async def test_get_access_token_persists_shared_db_cache_after_refresh():
    import services.wechat.wechat_notify as wn
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
    with patch("services.wechat.wechat_notify.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("services.wechat.wechat_notify.get_runtime_token", new=AsyncMock(return_value=None)), \
         patch("services.wechat.wechat_notify.upsert_runtime_token", mock_upsert), \
         patch("services.wechat.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        token = await wechat._get_access_token("appid", "secret")

    assert token == "fresh-token"
    mock_upsert.assert_awaited_once()


async def test_get_access_token_uses_wecom_kf_gettoken_for_corp_id():
    import services.wechat.wechat_notify as wn
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

    with patch("services.wechat.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        token = await wechat._get_access_token("ww-corp-id", "corp-secret")

    assert token == "kf-token"


# ---------------------------------------------------------------------------
# _send_customer_service_msg tests
# ---------------------------------------------------------------------------


async def test_send_customer_service_msg_raises_on_access_token_error():
    with patch("services.wechat.wechat_notify._get_access_token", new=AsyncMock(side_effect=RuntimeError("boom"))):
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
    with patch("services.wechat.wechat_notify._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat.wechat_notify.httpx.AsyncClient", return_value=client):
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

    with patch("services.wechat.wechat_notify._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat.wechat_notify.httpx.AsyncClient", return_value=_Client()):
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
        "services.wechat.wechat_notify._get_config",
        return_value={
            "token": "tok",
            "app_id": "ww-corp",
            "app_secret": "secret",
            "aes_key": "",
            "open_kfid": "",
            "is_kf": True,
        },
    ), patch("services.wechat.wechat_notify._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat.wechat_notify.httpx.AsyncClient", return_value=_Client()):
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
        "services.wechat.wechat_notify._get_config",
        return_value={
            "token": "tok",
            "app_id": "ww-corp",
            "app_secret": "secret",
            "aes_key": "",
            "open_kfid": "kf-001",
            "is_kf": True,
        },
    ), patch("services.wechat.wechat_notify._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat.wechat_notify.httpx.AsyncClient", return_value=_Client()):
        await wechat._send_customer_service_msg("u1", "hello")

    assert captured["payload"]["open_kfid"] == "kf-001"
