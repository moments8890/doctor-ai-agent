"""Runtime config: load config/runtime.json at startup, push to os.environ. No hot-reload."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.runtime_config_meta import (
    CATEGORY_DESCRIPTIONS_ZH,
    CONFIG_ALLOWED_VALUES,
    CONFIG_CATEGORIES,
    CONFIG_DESCRIPTIONS,
    CONFIG_DESCRIPTIONS_ZH,
)

ROOT = Path(__file__).resolve().parents[2]  # src/utils/runtime_config.py → project root
DEFAULT_CONFIG_PATH = ROOT / "config" / "runtime.json"

DEFAULT_RUNTIME_CONFIG: Dict[str, Any] = {
    "ROUTING_LLM": "groq",
    "STRUCTURING_LLM": "groq",
    "LLM_PROVIDER_STRICT_MODE": True,
    "VISION_LLM": "ollama",
    "OPENAI_API_KEY": "",
    "TENCENT_LKEAP_BASE_URL": "https://api.lkeap.cloud.tencent.com/v1",
    "TENCENT_LKEAP_MODEL": "deepseek-v3-1",
    "TENCENT_LKEAP_API_KEY": "",
    "GROQ_API_KEY": "",
    "DEEPSEEK_API_KEY": "",
    "CEREBRAS_API_KEY": "",
    "SAMBANOVA_API_KEY": "",
    "SILICONFLOW_API_KEY": "",
    "OPENROUTER_API_KEY": "",
    "OLLAMA_BASE_URL": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    "OLLAMA_VISION_BASE_URL": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    "OLLAMA_MODEL": "qwen3.5:9b",
    "OLLAMA_VISION_MODEL": "qwen3-vl:8b",
    "OLLAMA_API_KEY": "ollama",
    "GEMINI_VISION_MODEL": "gemini-2.0-flash",
    "PATIENTS_DB_PATH": str(ROOT / "patients.db"),
    "DATABASE_URL": "",
    "AUTO_FOLLOWUP_TASKS_ENABLED": False,
    "LOG_LEVEL": "INFO",
    "LOG_FORMAT": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    "LOG_TO_FILE": True,
    "LOG_DIR": "logs",
    "LOG_FILE": "app.log",
    "LOG_MAX_BYTES": 10485760,
    "LOG_BACKUP_COUNT": 5,
    "TASK_SCHEDULER_MODE": "interval",
    "TASK_SCHEDULER_INTERVAL_MINUTES": 1,
    "TASK_SCHEDULER_CRON": "*/1 * * * *",
    "TASK_SCHEDULER_LEASE_ENABLED": True,
    "TASK_SCHEDULER_LEASE_TTL_SECONDS": 90,
    "TASK_NOTIFY_RETRY_COUNT": 3,
    "TASK_NOTIFY_RETRY_DELAY_SECONDS": 1,
    "KNOWLEDGE_CANDIDATE_LIMIT": 30,
    "KNOWLEDGE_MAX_ITEMS": 3,
    "KNOWLEDGE_MAX_CHARS": 1200,
    "KNOWLEDGE_MAX_ITEM_CHARS": 320,
    "KNOWLEDGE_AUTO_LEARN_ENABLED": True,
    "KNOWLEDGE_AUTO_MAX_NEW_PER_TURN": 1,
    "KNOWLEDGE_AUTO_MIN_TEXT_CHARS": 8,
    "WECOM_CORP_ID": "",
    "WECOM_AGENT_ID": "",
    "WECOM_SECRET": "",
    "WECHAT_TOKEN": "",
    "WECHAT_AES_KEY": "",
    "NOTIFICATION_PROVIDER": "log",
    "WECHAT_NOTIFY_FALLBACK_TO_USER": "",
    "WECHAT_MINI_APP_ID": "",
    "WECHAT_MINI_APP_SECRET": "",
    "MINIPROGRAM_TOKEN_SECRET": "dev-miniprogram-secret",
    "MINIPROGRAM_TOKEN_TTL_SECONDS": 604800,
    "MINIPROGRAM_API_BASE_URL": "",
    "UI_ADMIN_TOKEN": "",
    "UI_DEBUG_TOKEN": "",
    "PATIENT_PORTAL_SECRET": "",
    "PENDING_RECORD_TTL_MINUTES": 30,
    "PHI_CLOUD_EGRESS_ALLOWED": False,
}


def runtime_config_path(path: Optional[str] = None) -> Path:
    if path:
        return Path(path).expanduser()
    return DEFAULT_CONFIG_PATH


def _build_structured(values: Dict[str, Any]) -> Dict[str, Any]:
    categories: Dict[str, Any] = {}
    assigned = set()
    for category_key, meta in CONFIG_CATEGORIES.items():
        settings: Dict[str, Any] = {}
        for key in meta["keys"]:
            item = {
                "value": values.get(key, DEFAULT_RUNTIME_CONFIG.get(key)),
                "description": CONFIG_DESCRIPTIONS.get(key, ""),
                "description_zh": CONFIG_DESCRIPTIONS_ZH.get(key, ""),
            }
            if key in CONFIG_ALLOWED_VALUES:
                item["options"] = CONFIG_ALLOWED_VALUES[key]
            settings[key] = item
            assigned.add(key)
        categories[category_key] = {
            "description": meta["description"],
            "description_zh": CATEGORY_DESCRIPTIONS_ZH.get(category_key, ""),
            "settings": settings,
        }

    extra_keys = sorted(k for k in values.keys() if k not in assigned)
    if extra_keys:
        categories["runtime_overrides"] = {
            "description": "Keys not part of the default catalog.",
            "settings": {
                key: {
                    "value": values[key],
                    "description": CONFIG_DESCRIPTIONS.get(key, ""),
                    "description_zh": CONFIG_DESCRIPTIONS_ZH.get(key, ""),
                    **({"options": CONFIG_ALLOWED_VALUES[key]} if key in CONFIG_ALLOWED_VALUES else {}),
                }
                for key in extra_keys
            },
        }

    return {
        "format": "doctor-ai-agent.runtime-config.v2",
        "description": "Runtime configuration catalog with grouped settings and inline descriptions.",
        "description_zh": "运行时配置目录，按分类组织并包含每项配置说明。",
        "categories": categories,
    }


def _flatten(payload: Dict[str, Any]) -> Dict[str, Any]:
    if "categories" not in payload:
        return {k: v for k, v in payload.items() if not isinstance(v, (dict, list))}

    out: Dict[str, Any] = {}
    categories = payload.get("categories")
    if not isinstance(categories, dict):
        return out
    for category in categories.values():
        if not isinstance(category, dict):
            continue
        settings = category.get("settings")
        if not isinstance(settings, dict):
            continue
        for key, item in settings.items():
            if isinstance(item, dict) and "value" in item:
                out[key] = item.get("value")
            elif not isinstance(item, (dict, list)):
                out[key] = item
    return out


def load_runtime_json(path: Optional[str] = None) -> Dict[str, Any]:
    target = runtime_config_path(path)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(_build_structured(DEFAULT_RUNTIME_CONFIG), ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(DEFAULT_RUNTIME_CONFIG)

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    flat = _flatten(payload)
    merged = dict(DEFAULT_RUNTIME_CONFIG)
    merged.update(flat)
    return merged


# ---------------------------------------------------------------------------
# Canonical config readers — single source of truth for cross-cutting knobs
# ---------------------------------------------------------------------------

_DEFAULT_OLLAMA_URL = DEFAULT_RUNTIME_CONFIG["OLLAMA_BASE_URL"]
_DEFAULT_OLLAMA_VISION_URL = DEFAULT_RUNTIME_CONFIG["OLLAMA_VISION_BASE_URL"]


def save_runtime_json(config: Dict[str, Any], path: Optional[str] = None) -> Path:
    target = runtime_config_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if target.exists():
        try:
            parsed = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                existing = parsed
        except Exception:
            existing = {}

    base_values = dict(DEFAULT_RUNTIME_CONFIG)
    base_values.update(_flatten(existing))
    base_values.update(config)
    structured = _build_structured(base_values)
    target.write_text(
        json.dumps(structured, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def runtime_config_source_path(path: Optional[str] = None) -> Path:
    return runtime_config_path(path)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _sanitize_scheduler_fields(sanitized: Dict[str, str]) -> None:
    """校验并规范化调度器相关字段（原地修改 sanitized）。"""
    mode = sanitized["TASK_SCHEDULER_MODE"].lower()
    sanitized["TASK_SCHEDULER_MODE"] = mode if mode in {"interval", "cron"} else "interval"

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


def _sanitize_knowledge_fields(sanitized: Dict[str, str]) -> None:
    """校验并规范化知识库相关整型字段（原地修改 sanitized）。"""
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
            parsed = int(DEFAULT_RUNTIME_CONFIG[key])
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
    sanitized: Dict[str, str] = {}
    merged = dict(DEFAULT_RUNTIME_CONFIG)
    merged.update(raw)
    for key, default in DEFAULT_RUNTIME_CONFIG.items():
        raw_value = merged.get(key, default)
        value = _stringify(raw_value)
        if not value and key in {"TASK_SCHEDULER_MODE", "TASK_SCHEDULER_INTERVAL_MINUTES", "TASK_SCHEDULER_CRON"}:
            value = _stringify(default)
        sanitized[key] = value

    _sanitize_scheduler_fields(sanitized)
    _sanitize_knowledge_fields(sanitized)
    _sanitize_bool_and_enum_fields(sanitized)
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


async def apply_runtime_config(config: Dict[str, str]) -> None:
    """Save config to os.environ. Takes full effect on next restart."""
    for key, value in config.items():
        os.environ[key] = value
