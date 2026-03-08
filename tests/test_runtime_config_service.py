from __future__ import annotations

from utils.runtime_config import runtime_config_categories, validate_runtime_config


def test_runtime_config_categories_include_options_for_restricted_keys():
    categories = runtime_config_categories(
        {
            "TASK_SCHEDULER_MODE": "interval",
            "NOTIFICATION_PROVIDER": "log",
            "AGENT_TOOL_SCHEMA_MODE": "full",
        }
    )
    flattened = {
        item["key"]: item
        for cat in categories
        for item in (cat.get("items") or [])
    }
    assert flattened["TASK_SCHEDULER_MODE"]["options"] == ["interval", "cron"]
    assert flattened["NOTIFICATION_PROVIDER"]["options"] == ["log", "wechat"]
    assert flattened["AGENT_TOOL_SCHEMA_MODE"]["options"] == ["full", "compact"]


def test_validate_runtime_config_rejects_invalid_enums():
    result = validate_runtime_config({"TASK_SCHEDULER_MODE": "bad-mode", "LOG_LEVEL": "trace"})
    assert result["ok"] is False
    assert any("TASK_SCHEDULER_MODE" in err for err in result["errors"])
    assert any("LOG_LEVEL" in err for err in result["errors"])
