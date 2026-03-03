from __future__ import annotations

import os

from services.wechat_notify import _send_customer_service_msg
from utils.log import log


def _provider() -> str:
    return os.environ.get("NOTIFICATION_PROVIDER", "log").strip().lower()


async def send_doctor_notification(doctor_id: str, message: str) -> None:
    """Send doctor notification via configured provider.

    Providers:
    - log (default): log-only sink for local/dev, always succeeds
    - wechat: send through WeChat customer service API
    """
    provider = _provider()
    if provider == "wechat":
        await _send_customer_service_msg(doctor_id, message)
        return

    if provider == "log":
        preview = message.replace("\n", " ")[:120]
        log(
            "[Notify:log] delivered",
            logger_name="tasks",
            doctor_id=doctor_id,
            preview=preview,
        )
        return

    raise RuntimeError(f"Unsupported NOTIFICATION_PROVIDER: {provider}")
