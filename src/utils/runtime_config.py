"""Runtime config: load/save config/runtime.json. No hot-reload.

Re-exports all public symbols so callers using ``from utils.runtime_config import X``
continue to work unchanged.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

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
    "TENCENT_LKEAP_MODEL": "deepseek-v3.2",
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
    "LOG_DIR": str(ROOT / "logs"),
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
    "MINIPROGRAM_API_BASE_URL": "",
    "UI_ADMIN_TOKEN": "",
    "UI_DEBUG_TOKEN": "",
    "PATIENT_PORTAL_SECRET": "",
    "PENDING_RECORD_TTL_MINUTES": 30,
    "PHI_CLOUD_EGRESS_ALLOWED": False,
    "EMBEDDING_PROVIDER": "local",
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    "EMBEDDING_PRELOAD": True,
    "DASHSCOPE_API_KEY": "",
    "SKILLS_CACHE_TTL": 300,
    "DIAGNOSIS_LLM": "",
}

# Canonical Ollama URL defaults — referenced by other modules
_DEFAULT_OLLAMA_URL = DEFAULT_RUNTIME_CONFIG["OLLAMA_BASE_URL"]
_DEFAULT_OLLAMA_VISION_URL = DEFAULT_RUNTIME_CONFIG["OLLAMA_VISION_BASE_URL"]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def runtime_config_path(path: Optional[str] = None) -> Path:
    if path:
        return Path(path).expanduser()
    return DEFAULT_CONFIG_PATH


def runtime_config_source_path(path: Optional[str] = None) -> Path:
    return runtime_config_path(path)


# ---------------------------------------------------------------------------
# Structured JSON format helpers (v2 catalog)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Core load / save
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Re-exports from focused sub-modules
# ---------------------------------------------------------------------------

from utils.runtime_config_validation import (  # noqa: E402
    _sanitize_config,
    load_runtime_config_dict,
    runtime_config_categories,
    save_runtime_config_dict,
    validate_runtime_config,
)
from utils.runtime_config_apply import apply_runtime_config  # noqa: E402

__all__ = [
    # core
    "DEFAULT_RUNTIME_CONFIG",
    "DEFAULT_CONFIG_PATH",
    "ROOT",
    "runtime_config_path",
    "runtime_config_source_path",
    "load_runtime_json",
    "save_runtime_json",
    # validation / categories
    "_sanitize_config",
    "load_runtime_config_dict",
    "runtime_config_categories",
    "save_runtime_config_dict",
    "validate_runtime_config",
    # apply
    "apply_runtime_config",
]
