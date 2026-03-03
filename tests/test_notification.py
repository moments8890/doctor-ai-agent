from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.notification import send_doctor_notification


async def test_send_doctor_notification_log_provider_succeeds():
    with patch.dict("os.environ", {"NOTIFICATION_PROVIDER": "log"}, clear=False), \
         patch("services.notification.log") as mock_log:
        await send_doctor_notification("doc1", "hello")

    mock_log.assert_called_once()


async def test_send_doctor_notification_wechat_provider_calls_wechat_sender():
    mock_send = AsyncMock()
    with patch.dict("os.environ", {"NOTIFICATION_PROVIDER": "wechat"}, clear=False), \
         patch("services.notification._send_customer_service_msg", mock_send):
        await send_doctor_notification("doc2", "hello")

    mock_send.assert_awaited_once_with("doc2", "hello")


async def test_send_doctor_notification_unknown_provider_raises():
    with patch.dict("os.environ", {"NOTIFICATION_PROVIDER": "unknown"}, clear=False):
        with pytest.raises(RuntimeError):
            await send_doctor_notification("doc3", "hello")
