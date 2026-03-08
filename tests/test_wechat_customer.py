"""
Tests for services/wechat_customer.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import services.wechat.wechat_customer as wc


def _reset_cache() -> None:
    wc._PROFILE_CACHE.clear()
    wc._NEGATIVE_CACHE.clear()


async def test_prefetch_customer_profile_success_and_cache_hit():
    _reset_cache()

    data = {
        "errcode": 0,
        "customer_list": [
            {
                "external_userid": "wm_u1",
                "nickname": "张三",
                "enter_session_context": {"scene": "123"},
            }
        ],
        "invalid_external_userid": [],
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
            assert params["access_token"] == "tok"
            assert json["external_userid_list"] == ["wm_u1"]
            return _Resp()

    with patch("services.wechat.wechat_customer._get_config", return_value={"app_id": "ww", "app_secret": "sec"}), \
         patch("services.wechat.wechat_customer._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat.wechat_customer.httpx.AsyncClient", return_value=_Client()):
        profile = await wc.prefetch_customer_profile("wm_u1")

    assert profile is not None
    assert profile["nickname"] == "张三"

    # Second read should hit cache even without HTTP client.
    with patch("services.wechat.wechat_customer.httpx.AsyncClient") as client_cls:
        cached = await wc.prefetch_customer_profile("wm_u1")
    assert cached is not None
    assert cached["nickname"] == "张三"
    client_cls.assert_not_called()


async def test_prefetch_customer_profile_invalid_user_sets_negative_cache():
    _reset_cache()

    data = {
        "errcode": 0,
        "customer_list": [],
        "invalid_external_userid": ["wm_u2"],
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

    with patch("services.wechat.wechat_customer._get_config", return_value={"app_id": "ww", "app_secret": "sec"}), \
         patch("services.wechat.wechat_customer._get_access_token", new=AsyncMock(return_value="tok")), \
         patch("services.wechat.wechat_customer.httpx.AsyncClient", return_value=_Client()):
        profile = await wc.prefetch_customer_profile("wm_u2")

    assert profile is None


async def test_prefetch_customer_profile_disabled_noop():
    _reset_cache()
    with patch.dict("os.environ", {"WECHAT_KF_ENABLE_CUSTOMER_ENRICH": "0"}, clear=False), \
         patch("services.wechat.wechat_customer.httpx.AsyncClient") as client_cls:
        profile = await wc.prefetch_customer_profile("wm_u3")
    assert profile is None
    client_cls.assert_not_called()
