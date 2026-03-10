"""通知控制策略测试：验证通知命令解析、cron 表达式解析及自动发送时机判断逻辑。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db.models import DoctorNotifyPreference
from services.notify.notify_control import (
    parse_notify_command,
    parse_simple_cron_minutes,
    should_auto_run_now,
)


def test_parse_notify_commands_variants():
    assert parse_notify_command("通知模式 手动") == ("set_mode", {"notify_mode": "manual"})
    assert parse_notify_command("通知模式:自动") == ("set_mode", {"notify_mode": "auto"})
    assert parse_notify_command("通知频率 每30分钟") == ("set_interval", {"interval_minutes": 30})
    assert parse_notify_command("通知计划 */5 * * * *") == ("set_cron", {"cron_expr": "*/5 * * * *"})
    assert parse_notify_command("通知计划 立即") == ("set_immediate", {})
    assert parse_notify_command("立即发送待办") == ("trigger_now", {})
    assert parse_notify_command("查看通知设置") == ("show", {})


def test_parse_simple_cron_minutes_supports_minute_granularity():
    assert parse_simple_cron_minutes("*/1 * * * *") == 1
    assert parse_simple_cron_minutes("*/15 * * * *") == 15
    assert parse_simple_cron_minutes("0 0 * * *") is None


def test_should_auto_run_now_respects_manual_interval_and_cron():
    now = datetime.now(timezone.utc)

    manual_pref = DoctorNotifyPreference(
        doctor_id="doc1",
        notify_mode="manual",
        schedule_type="immediate",
    )
    assert should_auto_run_now(manual_pref, now, include_manual=False) is False
    assert should_auto_run_now(manual_pref, now, include_manual=True) is True

    interval_pref = DoctorNotifyPreference(
        doctor_id="doc2",
        notify_mode="auto",
        schedule_type="interval",
        interval_minutes=10,
        last_auto_run_at=now - timedelta(minutes=5),
    )
    assert should_auto_run_now(interval_pref, now) is False
    interval_pref.last_auto_run_at = now - timedelta(minutes=10)
    assert should_auto_run_now(interval_pref, now) is True

    cron_pref = DoctorNotifyPreference(
        doctor_id="doc3",
        notify_mode="auto",
        schedule_type="cron",
        cron_expr="*/5 * * * *",
        last_auto_run_at=now - timedelta(minutes=3),
    )
    assert should_auto_run_now(cron_pref, now) is False
    cron_pref.last_auto_run_at = now - timedelta(minutes=5)
    assert should_auto_run_now(cron_pref, now) is True
