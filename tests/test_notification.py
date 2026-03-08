from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.notify.notification import send_doctor_notification


class _SessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_send_doctor_notification_log_provider_succeeds():
    with patch.dict("os.environ", {"NOTIFICATION_PROVIDER": "log"}, clear=False), \
         patch("services.notify.notification.log") as mock_log:
        await send_doctor_notification("doc1", "hello")

    mock_log.assert_called_once()


async def test_send_doctor_notification_wechat_provider_calls_wechat_sender():
    mock_send = AsyncMock()
    with patch.dict("os.environ", {"NOTIFICATION_PROVIDER": "wechat"}, clear=False), \
         patch("services.notify.notification.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("services.notify.notification.get_doctor_wechat_user_id", new=AsyncMock(return_value=None)), \
         patch("services.notify.notification._send_customer_service_msg", mock_send):
        await send_doctor_notification("doc2", "hello")

    mock_send.assert_awaited_once_with("doc2", "hello")


async def test_send_doctor_notification_wechat_falls_back_on_invalid_external_userid():
    mock_send = AsyncMock(side_effect=[
        RuntimeError("WeChat send failed: errcode=40096 errmsg=invalid external userid"),
        None,
    ])
    with patch.dict(
        "os.environ",
        {
            "NOTIFICATION_PROVIDER": "wechat",
            "WECHAT_NOTIFY_FALLBACK_TO_USER": "wm_valid_receiver",
        },
        clear=False,
    ), patch("services.notify.notification.AsyncSessionLocal", return_value=_SessionCtx()), \
        patch("services.notify.notification.get_doctor_wechat_user_id", new=AsyncMock(return_value=None)), \
        patch("services.notify.notification._send_customer_service_msg", mock_send):
        await send_doctor_notification("inttest_fake_doctor", "hello")

    assert mock_send.await_count == 2
    first = mock_send.await_args_list[0].args
    second = mock_send.await_args_list[1].args
    assert first == ("inttest_fake_doctor", "hello")
    assert second == ("wm_valid_receiver", "hello")


async def test_send_doctor_notification_wechat_non_40096_error_does_not_fallback():
    mock_send = AsyncMock(side_effect=RuntimeError("WeChat send failed: errcode=45015"))
    with patch.dict(
        "os.environ",
        {
            "NOTIFICATION_PROVIDER": "wechat",
            "WECHAT_NOTIFY_FALLBACK_TO_USER": "wm_valid_receiver",
        },
        clear=False,
    ), patch("services.notify.notification.AsyncSessionLocal", return_value=_SessionCtx()), \
        patch("services.notify.notification.get_doctor_wechat_user_id", new=AsyncMock(return_value=None)), \
        patch("services.notify.notification._send_customer_service_msg", mock_send):
        with pytest.raises(RuntimeError):
            await send_doctor_notification("inttest_fake_doctor", "hello")

    mock_send.assert_awaited_once_with("inttest_fake_doctor", "hello")


async def test_send_doctor_notification_unknown_provider_raises():
    with patch.dict("os.environ", {"NOTIFICATION_PROVIDER": "unknown"}, clear=False):
        with pytest.raises(RuntimeError):
            await send_doctor_notification("doc3", "hello")


async def test_send_doctor_notification_wechat_mini_subscribe_provider_calls_sender():
    mock_send = AsyncMock()
    with patch.dict(
        "os.environ",
        {
            "NOTIFICATION_PROVIDER": "wechat_mini_subscribe",
            "MINIPROGRAM_SUBSCRIBE_TEMPLATE_ID": "tpl_123",
        },
        clear=False,
    ), patch("services.notify.notification.AsyncSessionLocal", return_value=_SessionCtx()), \
        patch("services.notify.notification.get_doctor_wechat_user_id", new=AsyncMock(return_value="openid_mini_1")), \
        patch("services.notify.notification._send_miniprogram_subscribe_msg", mock_send):
        await send_doctor_notification("doc-mini", "hello mini")

    mock_send.assert_awaited_once_with("openid_mini_1", "hello mini")


async def test_send_doctor_notification_wechat_mini_subscribe_mapping_fail_fallbacks_to_doctor():
    mock_send = AsyncMock()
    with patch.dict(
        "os.environ",
        {
            "NOTIFICATION_PROVIDER": "wechat_mini_subscribe",
            "MINIPROGRAM_SUBSCRIBE_TEMPLATE_ID": "tpl_123",
        },
        clear=False,
    ), patch("services.notify.notification.AsyncSessionLocal", return_value=_SessionCtx()), \
        patch("services.notify.notification.get_doctor_wechat_user_id", new=AsyncMock(side_effect=RuntimeError("db down"))), \
        patch("services.notify.notification._send_miniprogram_subscribe_msg", mock_send), \
        patch("services.notify.notification.log") as mock_log:
        await send_doctor_notification("doc-mini-fallback", "hello mini")

    mock_send.assert_awaited_once_with("doc-mini-fallback", "hello mini")
    assert mock_log.call_count >= 1


async def test_send_doctor_notification_wechat_uses_mapped_wechat_user_id():
    mock_send = AsyncMock()
    with patch.dict("os.environ", {"NOTIFICATION_PROVIDER": "wechat"}, clear=False), \
         patch("services.notify.notification.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("services.notify.notification.get_doctor_wechat_user_id", new=AsyncMock(return_value="wm80mapped")), \
         patch("services.notify.notification._send_customer_service_msg", mock_send):
        await send_doctor_notification("doc-internal-id", "hello")

    mock_send.assert_awaited_once_with("wm80mapped", "hello")


async def test_send_doctor_notification_wechat_mapping_failure_falls_back_to_doctor_id():
    mock_send = AsyncMock()
    with patch.dict("os.environ", {"NOTIFICATION_PROVIDER": "wechat"}, clear=False), \
         patch("services.notify.notification.AsyncSessionLocal", return_value=_SessionCtx()), \
         patch("services.notify.notification.get_doctor_wechat_user_id", new=AsyncMock(side_effect=RuntimeError("db down"))), \
         patch("services.notify.notification._send_customer_service_msg", mock_send), \
         patch("services.notify.notification.log") as mock_log:
        await send_doctor_notification("doc-map-fallback", "hello")

    mock_send.assert_awaited_once_with("doc-map-fallback", "hello")
    assert mock_log.call_count >= 1
