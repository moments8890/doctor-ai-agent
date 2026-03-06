from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils.runtime_json import (
    CATEGORY_DESCRIPTIONS_ZH,
    CONFIG_ALLOWED_VALUES,
    CONFIG_CATEGORIES,
    CONFIG_DESCRIPTIONS,
    CONFIG_DESCRIPTIONS_ZH,
    DEFAULT_RUNTIME_CONFIG,
    load_runtime_json,
    save_runtime_json,
    runtime_config_path,
)

_RuntimeHook = Callable[[Dict[str, str]], Any]
_runtime_apply_hooks: list[_RuntimeHook] = []


def allowed_runtime_config_keys() -> list[str]:
    return sorted(DEFAULT_RUNTIME_CONFIG.keys())


def runtime_config_source_path(path: Optional[str] = None) -> Path:
    return runtime_config_path(path)


def register_runtime_apply_hook(hook: _RuntimeHook) -> None:
    _runtime_apply_hooks.append(hook)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _sanitize_config(raw: Dict[str, Any]) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}
    merged = dict(DEFAULT_RUNTIME_CONFIG)
    merged.update(raw)
    for key, default in DEFAULT_RUNTIME_CONFIG.items():
        raw_value = merged.get(key, default)
        value = _stringify(raw_value)
        if not value and key in {"TASK_SCHEDULER_MODE", "TASK_SCHEDULER_INTERVAL_MINUTES", "TASK_SCHEDULER_CRON"}:
            value = _stringify(default)
        sanitized[key] = value

    mode = sanitized["TASK_SCHEDULER_MODE"].lower()
    if mode not in {"interval", "cron"}:
        mode = "interval"
    sanitized["TASK_SCHEDULER_MODE"] = mode

    try:
        interval_minutes = max(1, int(sanitized["TASK_SCHEDULER_INTERVAL_MINUTES"]))
    except (TypeError, ValueError):
        interval_minutes = int(DEFAULT_RUNTIME_CONFIG["TASK_SCHEDULER_INTERVAL_MINUTES"])
    sanitized["TASK_SCHEDULER_INTERVAL_MINUTES"] = str(interval_minutes)

    cron_expr = sanitized["TASK_SCHEDULER_CRON"] or str(DEFAULT_RUNTIME_CONFIG["TASK_SCHEDULER_CRON"])
    if len(cron_expr.split()) != 5:
        cron_expr = str(DEFAULT_RUNTIME_CONFIG["TASK_SCHEDULER_CRON"])
    sanitized["TASK_SCHEDULER_CRON"] = cron_expr

    try:
        lease_ttl = max(10, int(sanitized["TASK_SCHEDULER_LEASE_TTL_SECONDS"]))
    except (TypeError, ValueError):
        lease_ttl = int(DEFAULT_RUNTIME_CONFIG["TASK_SCHEDULER_LEASE_TTL_SECONDS"])
    sanitized["TASK_SCHEDULER_LEASE_TTL_SECONDS"] = str(lease_ttl)

    try:
        retry_count = max(1, int(sanitized["TASK_NOTIFY_RETRY_COUNT"]))
    except (TypeError, ValueError):
        retry_count = int(DEFAULT_RUNTIME_CONFIG["TASK_NOTIFY_RETRY_COUNT"])
    sanitized["TASK_NOTIFY_RETRY_COUNT"] = str(retry_count)

    try:
        retry_delay = max(0.0, float(sanitized["TASK_NOTIFY_RETRY_DELAY_SECONDS"]))
    except (TypeError, ValueError):
        retry_delay = float(DEFAULT_RUNTIME_CONFIG["TASK_NOTIFY_RETRY_DELAY_SECONDS"])
    sanitized["TASK_NOTIFY_RETRY_DELAY_SECONDS"] = str(retry_delay)

    for key, minimum in (
        ("KNOWLEDGE_CANDIDATE_LIMIT", 1),
        ("KNOWLEDGE_MAX_ITEMS", 1),
        ("KNOWLEDGE_MAX_CHARS", 200),
        ("KNOWLEDGE_MAX_ITEM_CHARS", 80),
        ("KNOWLEDGE_AUTO_MAX_NEW_PER_TURN", 1),
        ("KNOWLEDGE_AUTO_MIN_TEXT_CHARS", 4),
    ):
        try:
            parsed = int(sanitized[key])
            parsed = max(minimum, parsed)
        except (TypeError, ValueError):
            parsed = int(DEFAULT_RUNTIME_CONFIG[key])
        sanitized[key] = str(parsed)

    provider = sanitized["NOTIFICATION_PROVIDER"].lower()
    sanitized["NOTIFICATION_PROVIDER"] = provider if provider in {"log", "wechat"} else "log"

    lease_enabled = sanitized["TASK_SCHEDULER_LEASE_ENABLED"].lower()
    sanitized["TASK_SCHEDULER_LEASE_ENABLED"] = "true" if lease_enabled in {"1", "true", "yes", "on"} else "false"
    strict_mode = sanitized["LLM_PROVIDER_STRICT_MODE"].lower()
    sanitized["LLM_PROVIDER_STRICT_MODE"] = "true" if strict_mode in {"1", "true", "yes", "on"} else "false"
    auto_learn = sanitized["KNOWLEDGE_AUTO_LEARN_ENABLED"].lower()
    sanitized["KNOWLEDGE_AUTO_LEARN_ENABLED"] = "true" if auto_learn in {"1", "true", "yes", "on"} else "false"

    log_level = sanitized["LOG_LEVEL"].upper()
    sanitized["LOG_LEVEL"] = log_level if log_level in CONFIG_ALLOWED_VALUES["LOG_LEVEL"] else "INFO"

    return sanitized


def _input_type_for_key(key: str) -> str:
    default = DEFAULT_RUNTIME_CONFIG.get(key)
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, (int, float)):
        return "number"
    return "string"


def runtime_config_categories(config: Dict[str, str]) -> List[Dict[str, Any]]:
    used = set()
    output: List[Dict[str, Any]] = []
    for category_key, meta in CONFIG_CATEGORIES.items():
        keys = list(meta.get("keys") or [])
        items = []
        for key in keys:
            item = {
                "key": key,
                "value": config.get(key, ""),
                "description": CONFIG_DESCRIPTIONS.get(key, ""),
                "description_zh": CONFIG_DESCRIPTIONS_ZH.get(key, ""),
                "input_type": _input_type_for_key(key),
            }
            if key in CONFIG_ALLOWED_VALUES:
                item["options"] = CONFIG_ALLOWED_VALUES[key]
            items.append(item)
            used.add(key)
        output.append(
            {
                "key": category_key,
                "description": str(meta.get("description") or ""),
                "description_zh": CATEGORY_DESCRIPTIONS_ZH.get(category_key, ""),
                "items": items,
            }
        )

    extra_keys = sorted(k for k in config.keys() if k not in used)
    if extra_keys:
        output.append(
            {
                "key": "runtime_overrides",
                "description": "Keys outside default catalog.",
                "items": [
                    {
                        "key": key,
                        "value": config[key],
                        "description": CONFIG_DESCRIPTIONS.get(key, ""),
                        "description_zh": CONFIG_DESCRIPTIONS_ZH.get(key, ""),
                        "input_type": _input_type_for_key(key),
                        **({"options": CONFIG_ALLOWED_VALUES[key]} if key in CONFIG_ALLOWED_VALUES else {}),
                    }
                    for key in extra_keys
                ],
            }
        )

    return output


async def load_runtime_config_dict() -> Dict[str, str]:
    return _sanitize_config(load_runtime_json())


async def save_runtime_config_dict(raw: Dict[str, Any]) -> Dict[str, str]:
    sanitized = _sanitize_config(raw)
    save_runtime_json(sanitized)
    return sanitized


def validate_runtime_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(raw, dict):
        return {"ok": False, "errors": ["config must be a JSON object"], "warnings": warnings, "sanitized": {}}

    for key, allowed in CONFIG_ALLOWED_VALUES.items():
        if key not in raw:
            continue
        value = str(raw.get(key, ""))
        if key in {
            "ROUTING_LLM",
            "STRUCTURING_LLM",
            "INTENT_PROVIDER",
            "VISION_LLM",
            "LLM_PROVIDER_STRICT_MODE",
            "AGENT_ROUTING_PROMPT_MODE",
            "AGENT_TOOL_SCHEMA_MODE",
            "KNOWLEDGE_AUTO_LEARN_ENABLED",
            "WHISPER_DEVICE",
            "TASK_SCHEDULER_MODE",
            "NOTIFICATION_PROVIDER",
        }:
            value = value.lower()
        elif key == "LOG_LEVEL":
            value = value.upper()
        if value not in allowed:
            errors.append("{0}: unsupported value '{1}', allowed={2}".format(key, raw.get(key), ",".join(allowed)))

    mode = str(raw.get("TASK_SCHEDULER_MODE", DEFAULT_RUNTIME_CONFIG["TASK_SCHEDULER_MODE"])).lower()
    cron_expr = str(raw.get("TASK_SCHEDULER_CRON", DEFAULT_RUNTIME_CONFIG["TASK_SCHEDULER_CRON"]))
    if mode == "cron" and len(cron_expr.split()) != 5:
        errors.append("TASK_SCHEDULER_CRON: must contain 5 cron fields when TASK_SCHEDULER_MODE=cron")

    try:
        lease_ttl = int(raw.get("TASK_SCHEDULER_LEASE_TTL_SECONDS", DEFAULT_RUNTIME_CONFIG["TASK_SCHEDULER_LEASE_TTL_SECONDS"]))
        if lease_ttl < 10:
            warnings.append("TASK_SCHEDULER_LEASE_TTL_SECONDS < 10; will be clamped to 10")
    except (TypeError, ValueError):
        errors.append("TASK_SCHEDULER_LEASE_TTL_SECONDS: must be an integer")

    for key in (
        "KNOWLEDGE_CANDIDATE_LIMIT",
        "KNOWLEDGE_MAX_ITEMS",
        "KNOWLEDGE_MAX_CHARS",
        "KNOWLEDGE_MAX_ITEM_CHARS",
        "KNOWLEDGE_AUTO_MAX_NEW_PER_TURN",
        "KNOWLEDGE_AUTO_MIN_TEXT_CHARS",
    ):
        if key not in raw:
            continue
        try:
            int(raw.get(key))
        except (TypeError, ValueError):
            errors.append("{0}: must be an integer".format(key))

    sanitized = _sanitize_config(raw)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "sanitized": sanitized}


async def apply_runtime_config(config: Dict[str, str]) -> None:
    for key, value in config.items():
        os.environ[key] = value

    # Hot-reload in-memory caches that should reflect new config immediately.
    try:
        from services.wechat_notify import _token_cache

        _token_cache["token"] = ""
        _token_cache["expires_at"] = 0.0
    except Exception:
        pass

    try:
        from services import structuring as structuring_mod

        structuring_mod._PROMPT_CACHE = None
    except Exception:
        pass

    try:
        from services import neuro_structuring as neuro_mod

        neuro_mod._PROMPT_CACHE = None
    except Exception:
        pass

    for hook in _runtime_apply_hooks:
        try:
            result = hook(config)
            if inspect.isawaitable(result):
                await result  # type: ignore[func-returns-value]
        except Exception:
            # Keep endpoint robust even when one hook fails.
            continue
