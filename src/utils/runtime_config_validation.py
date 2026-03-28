"""Runtime config validation, sanitization, and category building."""
from __future__ import annotations

from typing import Any, Dict, List

from utils.runtime_config_meta import (
    CATEGORY_DESCRIPTIONS_ZH,
    CONFIG_ALLOWED_VALUES,
    CONFIG_CATEGORIES,
    CONFIG_DESCRIPTIONS,
    CONFIG_DESCRIPTIONS_ZH,
)


def _get_defaults() -> Dict[str, Any]:
    # Late import to avoid circular dependency with runtime_config.py
    from utils.runtime_config import DEFAULT_RUNTIME_CONFIG
    return DEFAULT_RUNTIME_CONFIG


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _input_type_for_key(key: str) -> str:
    default = _get_defaults().get(key)
    if isinstance(default, bool):
        return "boolean"
    if isinstance(default, (int, float)):
        return "number"
    return "string"


# ---------------------------------------------------------------------------
# Sanitize helpers (in-place on a str→str dict)
# ---------------------------------------------------------------------------

def _sanitize_scheduler_fields(sanitized: Dict[str, str]) -> None:
    """校验并规范化调度器相关字段（原地修改 sanitized）。"""
    defaults = _get_defaults()
    mode = sanitized["TASK_SCHEDULER_MODE"].lower()
    sanitized["TASK_SCHEDULER_MODE"] = mode if mode in {"interval", "cron"} else "interval"

    try:
        interval_minutes = max(1, int(sanitized["TASK_SCHEDULER_INTERVAL_MINUTES"]))
    except (TypeError, ValueError):
        interval_minutes = int(defaults["TASK_SCHEDULER_INTERVAL_MINUTES"])
    sanitized["TASK_SCHEDULER_INTERVAL_MINUTES"] = str(interval_minutes)

    cron_expr = sanitized["TASK_SCHEDULER_CRON"] or str(defaults["TASK_SCHEDULER_CRON"])
    if len(cron_expr.split()) != 5:
        cron_expr = str(defaults["TASK_SCHEDULER_CRON"])
    sanitized["TASK_SCHEDULER_CRON"] = cron_expr

    try:
        lease_ttl = max(10, int(sanitized["TASK_SCHEDULER_LEASE_TTL_SECONDS"]))
    except (TypeError, ValueError):
        lease_ttl = int(defaults["TASK_SCHEDULER_LEASE_TTL_SECONDS"])
    sanitized["TASK_SCHEDULER_LEASE_TTL_SECONDS"] = str(lease_ttl)

    try:
        retry_count = max(1, int(sanitized["TASK_NOTIFY_RETRY_COUNT"]))
    except (TypeError, ValueError):
        retry_count = int(defaults["TASK_NOTIFY_RETRY_COUNT"])
    sanitized["TASK_NOTIFY_RETRY_COUNT"] = str(retry_count)

    try:
        retry_delay = max(0.0, float(sanitized["TASK_NOTIFY_RETRY_DELAY_SECONDS"]))
    except (TypeError, ValueError):
        retry_delay = float(defaults["TASK_NOTIFY_RETRY_DELAY_SECONDS"])
    sanitized["TASK_NOTIFY_RETRY_DELAY_SECONDS"] = str(retry_delay)


def _sanitize_knowledge_fields(sanitized: Dict[str, str]) -> None:
    """校验并规范化知识库相关整型字段（原地修改 sanitized）。"""
    defaults = _get_defaults()
    for key, minimum in (
        ("KNOWLEDGE_CANDIDATE_LIMIT", 1),
        ("KNOWLEDGE_MAX_ITEMS", 1),
        ("KNOWLEDGE_MAX_CHARS", 200),
        ("KNOWLEDGE_MAX_ITEM_CHARS", 80),
        ("KNOWLEDGE_AUTO_MAX_NEW_PER_TURN", 1),
        ("KNOWLEDGE_AUTO_MIN_TEXT_CHARS", 4),
    ):
        try:
            parsed = max(minimum, int(sanitized[key]))
        except (TypeError, ValueError):
            parsed = int(defaults[key])
        sanitized[key] = str(parsed)


def _sanitize_bool_and_enum_fields(sanitized: Dict[str, str]) -> None:
    """规范化布尔值与枚举字段（原地修改 sanitized）。"""
    _TRUE_VALS = {"1", "true", "yes", "on"}
    for key in ("TASK_SCHEDULER_LEASE_ENABLED", "LLM_PROVIDER_STRICT_MODE", "KNOWLEDGE_AUTO_LEARN_ENABLED"):
        sanitized[key] = "true" if sanitized[key].lower() in _TRUE_VALS else "false"

    provider = sanitized["NOTIFICATION_PROVIDER"].lower()
    sanitized["NOTIFICATION_PROVIDER"] = provider if provider in {"log", "wechat"} else "log"

    log_level = sanitized["LOG_LEVEL"].upper()
    sanitized["LOG_LEVEL"] = log_level if log_level in CONFIG_ALLOWED_VALUES["LOG_LEVEL"] else "INFO"


def _sanitize_config(raw: Dict[str, Any]) -> Dict[str, str]:
    """将原始配置字典规范化为合法的 str→str 字典，确保所有字段均有效。"""
    defaults = _get_defaults()
    sanitized: Dict[str, str] = {}
    merged = dict(defaults)
    merged.update(raw)
    for key, default in defaults.items():
        raw_value = merged.get(key, default)
        value = _stringify(raw_value)
        if not value and key in {"TASK_SCHEDULER_MODE", "TASK_SCHEDULER_INTERVAL_MINUTES", "TASK_SCHEDULER_CRON"}:
            value = _stringify(default)
        sanitized[key] = value

    _sanitize_scheduler_fields(sanitized)
    _sanitize_knowledge_fields(sanitized)
    _sanitize_bool_and_enum_fields(sanitized)
    return sanitized


# ---------------------------------------------------------------------------
# Category builder for UI
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Async dict-level load/save (used by admin API)
# ---------------------------------------------------------------------------

async def load_runtime_config_dict() -> Dict[str, str]:
    from utils.runtime_config import load_runtime_json
    return _sanitize_config(load_runtime_json())


async def save_runtime_config_dict(raw: Dict[str, Any]) -> Dict[str, str]:
    from utils.runtime_config import save_runtime_json
    sanitized = _sanitize_config(raw)
    save_runtime_json(sanitized)
    return sanitized


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_LOWER_CASE_ENUM_KEYS = {
    "ROUTING_LLM", "STRUCTURING_LLM", "VISION_LLM",
    "LLM_PROVIDER_STRICT_MODE",
    "KNOWLEDGE_AUTO_LEARN_ENABLED", "TASK_SCHEDULER_MODE",
    "NOTIFICATION_PROVIDER",
}


def _validate_enum_fields(raw: Dict[str, Any], errors: List[str]) -> None:
    """将允许值列表中的字段与提交值比对，将违规项追加到 errors。"""
    for key, allowed in CONFIG_ALLOWED_VALUES.items():
        if key not in raw:
            continue
        value = str(raw.get(key, ""))
        if key in _LOWER_CASE_ENUM_KEYS:
            value = value.lower()
        elif key == "LOG_LEVEL":
            value = value.upper()
        if value not in allowed:
            errors.append("{0}: unsupported value '{1}', allowed={2}".format(key, raw.get(key), ",".join(allowed)))


def _validate_scheduler_fields(raw: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    """校验调度器字段的语义合法性，将问题追加到 errors / warnings。"""
    defaults = _get_defaults()
    mode = str(raw.get("TASK_SCHEDULER_MODE", defaults["TASK_SCHEDULER_MODE"])).lower()
    cron_expr = str(raw.get("TASK_SCHEDULER_CRON", defaults["TASK_SCHEDULER_CRON"]))
    if mode == "cron" and len(cron_expr.split()) != 5:
        errors.append("TASK_SCHEDULER_CRON: must contain 5 cron fields when TASK_SCHEDULER_MODE=cron")
    try:
        lease_ttl = int(raw.get("TASK_SCHEDULER_LEASE_TTL_SECONDS", defaults["TASK_SCHEDULER_LEASE_TTL_SECONDS"]))
        if lease_ttl < 10:
            warnings.append("TASK_SCHEDULER_LEASE_TTL_SECONDS < 10; will be clamped to 10")
    except (TypeError, ValueError):
        errors.append("TASK_SCHEDULER_LEASE_TTL_SECONDS: must be an integer")
    for key in (
        "KNOWLEDGE_CANDIDATE_LIMIT", "KNOWLEDGE_MAX_ITEMS", "KNOWLEDGE_MAX_CHARS",
        "KNOWLEDGE_MAX_ITEM_CHARS", "KNOWLEDGE_AUTO_MAX_NEW_PER_TURN", "KNOWLEDGE_AUTO_MIN_TEXT_CHARS",
    ):
        if key not in raw:
            continue
        try:
            int(raw.get(key))
        except (TypeError, ValueError):
            errors.append("{0}: must be an integer".format(key))


def validate_runtime_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """校验原始配置字典，返回含 ok / errors / warnings / sanitized 的结果字典。"""
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(raw, dict):
        return {"ok": False, "errors": ["config must be a JSON object"], "warnings": warnings, "sanitized": {}}

    _validate_enum_fields(raw, errors)
    _validate_scheduler_fields(raw, errors, warnings)
    sanitized = _sanitize_config(raw)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "sanitized": sanitized}
