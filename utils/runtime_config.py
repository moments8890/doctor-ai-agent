from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "runtime.json"

DEFAULT_RUNTIME_CONFIG: Dict[str, Any] = {
    "ROUTING_LLM": "ollama",
    "STRUCTURING_LLM": "ollama",
    "INTENT_PROVIDER": "local",
    "LLM_PROVIDER_STRICT_MODE": True,
    "AGENT_ROUTING_PROMPT_MODE": "full",
    "AGENT_TOOL_SCHEMA_MODE": "compact",
    "VISION_LLM": "ollama",
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "OPENAI_MODEL": "gpt-5-codex",
    "OPENAI_API_KEY": "",
    "TENCENT_LKEAP_BASE_URL": "https://api.lkeap.cloud.tencent.com/v1",
    "TENCENT_LKEAP_MODEL": "deepseek-v3-1",
    "TENCENT_LKEAP_API_KEY": "",
    "GROQ_API_KEY": "",
    "DEEPSEEK_API_KEY": "",
    "GEMINI_API_KEY": "",
    "OLLAMA_BASE_URL": "http://192.168.0.123:11434/v1",
    "OLLAMA_VISION_BASE_URL": "http://192.168.0.123:11434/v1",
    "OLLAMA_MODEL": "qwen2.5:14b",
    "OLLAMA_VISION_MODEL": "qwen2.5vl:7b",
    "OLLAMA_API_KEY": "ollama",
    "GEMINI_VISION_MODEL": "gemini-2.0-flash",
    "PATIENTS_DB_PATH": str(ROOT / "patients.db"),
    "DATABASE_URL": "",
    "WHISPER_MODEL": "large-v3",
    "WHISPER_DEVICE": "cpu",
    "WHISPER_COMPUTE_TYPE": "int8",
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
    "MINIPROGRAM_API_BASE_URL": "https://nano-redhead-attitudes-attachment.trycloudflare.com",
    "UI_ADMIN_TOKEN": "",
    "UI_DEBUG_TOKEN": "",
}

CONFIG_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "llm": {
        "description": "LLM provider routing and model selection.",
        "keys": [
            "ROUTING_LLM",
            "STRUCTURING_LLM",
            "INTENT_PROVIDER",
            "LLM_PROVIDER_STRICT_MODE",
            "AGENT_ROUTING_PROMPT_MODE",
            "AGENT_TOOL_SCHEMA_MODE",
            "VISION_LLM",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_API_KEY",
            "TENCENT_LKEAP_BASE_URL",
            "TENCENT_LKEAP_MODEL",
            "TENCENT_LKEAP_API_KEY",
            "GROQ_API_KEY",
            "DEEPSEEK_API_KEY",
            "GEMINI_API_KEY",
            "OLLAMA_BASE_URL",
            "OLLAMA_VISION_BASE_URL",
            "OLLAMA_MODEL",
            "OLLAMA_VISION_MODEL",
            "OLLAMA_API_KEY",
            "GEMINI_VISION_MODEL",
        ],
    },
    "storage": {
        "description": "Database and storage path settings.",
        "keys": ["DATABASE_URL", "PATIENTS_DB_PATH"],
    },
    "speech": {
        "description": "ASR transcription model runtime settings.",
        "keys": ["WHISPER_MODEL", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE"],
    },
    "automation": {
        "description": "Clinical automation and scheduler behavior.",
        "keys": [
            "AUTO_FOLLOWUP_TASKS_ENABLED",
            "TASK_SCHEDULER_MODE",
            "TASK_SCHEDULER_INTERVAL_MINUTES",
            "TASK_SCHEDULER_CRON",
            "TASK_SCHEDULER_LEASE_ENABLED",
            "TASK_SCHEDULER_LEASE_TTL_SECONDS",
            "TASK_NOTIFY_RETRY_COUNT",
            "TASK_NOTIFY_RETRY_DELAY_SECONDS",
            "KNOWLEDGE_CANDIDATE_LIMIT",
            "KNOWLEDGE_MAX_ITEMS",
            "KNOWLEDGE_MAX_CHARS",
            "KNOWLEDGE_MAX_ITEM_CHARS",
            "KNOWLEDGE_AUTO_LEARN_ENABLED",
            "KNOWLEDGE_AUTO_MAX_NEW_PER_TURN",
            "KNOWLEDGE_AUTO_MIN_TEXT_CHARS",
        ],
    },
    "wecom": {
        "description": "WeCom (企业微信) custom app integration for internal doctor messaging.",
        "keys": [
            "WECOM_CORP_ID",
            "WECOM_AGENT_ID",
            "WECOM_SECRET",
            "WECHAT_TOKEN",
            "WECHAT_AES_KEY",
            "NOTIFICATION_PROVIDER",
            "WECHAT_NOTIFY_FALLBACK_TO_USER",
        ],
    },
    "miniprogram": {
        "description": "WeChat Mini Program authentication and endpoint defaults.",
        "keys": [
            "WECHAT_MINI_APP_ID",
            "WECHAT_MINI_APP_SECRET",
            "MINIPROGRAM_TOKEN_SECRET",
            "MINIPROGRAM_TOKEN_TTL_SECONDS",
            "MINIPROGRAM_API_BASE_URL",
        ],
    },
    "ui_auth": {
        "description": "Tokens for the admin and debug web UIs.",
        "description_zh": "Admin 和 Debug Web UI 的访问令牌。",
        "keys": [
            "UI_ADMIN_TOKEN",
            "UI_DEBUG_TOKEN",
        ],
    },
    "logging": {
        "description": "Application logging and rotation.",
        "keys": [
            "LOG_LEVEL",
            "LOG_FORMAT",
            "LOG_TO_FILE",
            "LOG_DIR",
            "LOG_FILE",
            "LOG_MAX_BYTES",
            "LOG_BACKUP_COUNT",
        ],
    },
}

CATEGORY_DESCRIPTIONS_ZH: Dict[str, str] = {
    "llm": "LLM 提供商路由与模型选择。",
    "storage": "数据库与存储路径配置。",
    "speech": "语音转写模型运行配置。",
    "automation": "临床自动化与调度行为。",
    "wecom": "企业微信自建应用集成与通知配置。",
    "miniprogram": "微信小程序鉴权与端点默认配置。",
    "logging": "应用日志与滚动策略。",
}

CONFIG_DESCRIPTIONS: Dict[str, str] = {
    "ROUTING_LLM": "Provider for intent/tool routing. Note: Ollama is LAN/local LLM (can be slower); DeepSeek is online LLM (billed).",
    "STRUCTURING_LLM": "Provider for medical record structuring. Note: Ollama is LAN/local LLM (can be slower); DeepSeek is online LLM (billed).",
    "INTENT_PROVIDER": "Intent mode: local or model-driven.",
    "LLM_PROVIDER_STRICT_MODE": "When true, use selected provider only and never fallback to others.",
    "AGENT_ROUTING_PROMPT_MODE": "Routing prompt verbosity mode: full or compact.",
    "AGENT_TOOL_SCHEMA_MODE": "Tool schema verbosity mode: full or compact.",
    "VISION_LLM": "Provider for image understanding.",
    "OPENAI_BASE_URL": "OpenAI API base URL.",
    "OPENAI_MODEL": "OpenAI/Codex model name for routing/structuring.",
    "OPENAI_API_KEY": "OpenAI API key.",
    "TENCENT_LKEAP_BASE_URL": "Tencent LKEAP OpenAI-compatible API base URL.",
    "TENCENT_LKEAP_MODEL": "Tencent LKEAP model name for routing/structuring.",
    "TENCENT_LKEAP_API_KEY": "Tencent LKEAP API key.",
    "GROQ_API_KEY": "Groq API key.",
    "DEEPSEEK_API_KEY": "DeepSeek API key.",
    "GEMINI_API_KEY": "Gemini API key.",
    "OLLAMA_BASE_URL": "OpenAI-compatible Ollama endpoint (typically LAN/local deployment).",
    "OLLAMA_VISION_BASE_URL": "Vision endpoint (can match OLLAMA_BASE_URL).",
    "OLLAMA_MODEL": "Primary text model name.",
    "OLLAMA_VISION_MODEL": "Primary vision model name.",
    "OLLAMA_API_KEY": "API key for Ollama-compatible client.",
    "GEMINI_VISION_MODEL": "Gemini model for vision route.",
    "DATABASE_URL": "Shared DB URL (recommended in multi-instance).",
    "PATIENTS_DB_PATH": "SQLite DB path when DATABASE_URL is empty.",
    "WHISPER_MODEL": "Faster-Whisper model size.",
    "WHISPER_DEVICE": "ASR device (cpu/cuda).",
    "WHISPER_COMPUTE_TYPE": "ASR compute type (int8/float16/etc.).",
    "AUTO_FOLLOWUP_TASKS_ENABLED": "Enable auto follow-up task generation.",
    "TASK_SCHEDULER_MODE": "Scheduler mode: interval or cron.",
    "TASK_SCHEDULER_INTERVAL_MINUTES": "Interval mode cadence in minutes.",
    "TASK_SCHEDULER_CRON": "Cron expression used in cron mode.",
    "TASK_SCHEDULER_LEASE_ENABLED": "Enable distributed lease to avoid duplicate runs.",
    "TASK_SCHEDULER_LEASE_TTL_SECONDS": "Lease TTL for failover recovery.",
    "TASK_NOTIFY_RETRY_COUNT": "Retry attempts for notification sends.",
    "TASK_NOTIFY_RETRY_DELAY_SECONDS": "Delay between retries.",
    "KNOWLEDGE_CANDIDATE_LIMIT": "How many knowledge items to scan per doctor before ranking.",
    "KNOWLEDGE_MAX_ITEMS": "Maximum number of knowledge snippets injected into routing prompt.",
    "KNOWLEDGE_MAX_CHARS": "Total character budget for injected knowledge prompt section.",
    "KNOWLEDGE_MAX_ITEM_CHARS": "Per-knowledge-item character cap before prompt injection.",
    "KNOWLEDGE_AUTO_LEARN_ENABLED": "Enable automatic knowledge capture from successful clinical turns.",
    "KNOWLEDGE_AUTO_MAX_NEW_PER_TURN": "Maximum auto-learned snippets inserted per chat turn.",
    "KNOWLEDGE_AUTO_MIN_TEXT_CHARS": "Minimum user-text length to consider for auto-learning.",
    "WECOM_CORP_ID": "WeCom CorpID (starts with ww), from 我的企业 → 企业信息.",
    "WECOM_AGENT_ID": "WeCom app AgentID, from 应用管理 → your app.",
    "WECOM_SECRET": "WeCom app Secret, from 应用管理 → your app.",
    "WECHAT_TOKEN": "Callback verification Token (set freely in WeCom app callback config).",
    "WECHAT_AES_KEY": "Callback EncodingAESKey (43 chars, generated in WeCom app callback config).",
    "NOTIFICATION_PROVIDER": "Notification backend (log or wechat).",
    "WECHAT_NOTIFY_FALLBACK_TO_USER": "Fallback external_userid for failed direct recipient.",
    "WECHAT_MINI_APP_ID": "Mini Program appid used by code2session.",
    "WECHAT_MINI_APP_SECRET": "Mini Program appsecret used by code2session.",
    "MINIPROGRAM_TOKEN_SECRET": "Signing key for mini access tokens.",
    "MINIPROGRAM_TOKEN_TTL_SECONDS": "Mini access token expiration in seconds.",
    "MINIPROGRAM_API_BASE_URL": "Public HTTPS API base URL used by mini client config.",
    "UI_ADMIN_TOKEN": "Bearer token required for admin UI endpoints (X-Admin-Token header).",
    "UI_DEBUG_TOKEN": "Bearer token required for debug UI endpoints (X-Debug-Token header). Grants access to /debug page — metrics, observability, logs.",
    "LOG_LEVEL": "Root logging level.",
    "LOG_FORMAT": "Python logging formatter string.",
    "LOG_TO_FILE": "Enable rotating file logging.",
    "LOG_DIR": "Directory for log files.",
    "LOG_FILE": "Primary app log filename.",
    "LOG_MAX_BYTES": "Max bytes per log file before rotation.",
    "LOG_BACKUP_COUNT": "Number of rotated log backups to keep.",
}

CONFIG_DESCRIPTIONS_ZH: Dict[str, str] = {
    "ROUTING_LLM": "意图/工具路由使用的提供商。说明：Ollama 通常是局域网/本地 LLM（可能较慢）；DeepSeek 是在线 LLM（按量计费）。",
    "STRUCTURING_LLM": "病历结构化使用的提供商。说明：Ollama 通常是局域网/本地 LLM（可能较慢）；DeepSeek 是在线 LLM（按量计费）。",
    "INTENT_PROVIDER": "意图模式：local 或 model-driven。",
    "LLM_PROVIDER_STRICT_MODE": "为 true 时仅使用所选提供商，不会自动回退到其它提供商。",
    "AGENT_ROUTING_PROMPT_MODE": "路由提示词详细度：full 或 compact。",
    "AGENT_TOOL_SCHEMA_MODE": "工具 schema 详细度：full 或 compact。",
    "VISION_LLM": "图像理解使用的提供商。",
    "OPENAI_BASE_URL": "OpenAI API 基地址。",
    "OPENAI_MODEL": "路由/结构化使用的 OpenAI/Codex 模型名。",
    "OPENAI_API_KEY": "OpenAI API Key。",
    "TENCENT_LKEAP_BASE_URL": "腾讯云 LKEAP（OpenAI 兼容）API 基地址。",
    "TENCENT_LKEAP_MODEL": "路由/结构化使用的腾讯云 LKEAP 模型名。",
    "TENCENT_LKEAP_API_KEY": "腾讯云 LKEAP API Key。",
    "GROQ_API_KEY": "Groq API Key。",
    "DEEPSEEK_API_KEY": "DeepSeek API Key。",
    "GEMINI_API_KEY": "Gemini API Key。",
    "OLLAMA_BASE_URL": "兼容 OpenAI 协议的 Ollama 地址（通常为局域网/本地部署）。",
    "OLLAMA_VISION_BASE_URL": "视觉模型地址（可与 OLLAMA_BASE_URL 相同）。",
    "OLLAMA_MODEL": "主文本模型名称。",
    "OLLAMA_VISION_MODEL": "主视觉模型名称。",
    "OLLAMA_API_KEY": "Ollama 客户端 API Key。",
    "GEMINI_VISION_MODEL": "视觉路由使用的 Gemini 模型。",
    "DATABASE_URL": "共享数据库 URL（多实例推荐）。",
    "PATIENTS_DB_PATH": "DATABASE_URL 为空时使用的 SQLite 路径。",
    "WHISPER_MODEL": "Faster-Whisper 模型规格。",
    "WHISPER_DEVICE": "ASR 设备（cpu/cuda）。",
    "WHISPER_COMPUTE_TYPE": "ASR 计算类型（int8/float16 等）。",
    "AUTO_FOLLOWUP_TASKS_ENABLED": "是否开启自动生成随访任务。",
    "TASK_SCHEDULER_MODE": "调度模式：interval 或 cron。",
    "TASK_SCHEDULER_INTERVAL_MINUTES": "interval 模式的分钟间隔。",
    "TASK_SCHEDULER_CRON": "cron 模式表达式。",
    "TASK_SCHEDULER_LEASE_ENABLED": "是否启用分布式租约防重复执行。",
    "TASK_SCHEDULER_LEASE_TTL_SECONDS": "租约 TTL（故障恢复用）。",
    "TASK_NOTIFY_RETRY_COUNT": "通知失败重试次数。",
    "TASK_NOTIFY_RETRY_DELAY_SECONDS": "重试间隔秒数。",
    "KNOWLEDGE_CANDIDATE_LIMIT": "每次检索医生知识库时参与排序的候选条数。",
    "KNOWLEDGE_MAX_ITEMS": "注入路由 prompt 的知识片段最大条数。",
    "KNOWLEDGE_MAX_CHARS": "注入知识片段的总字符预算上限。",
    "KNOWLEDGE_MAX_ITEM_CHARS": "单条知识片段注入前的字符截断上限。",
    "KNOWLEDGE_AUTO_LEARN_ENABLED": "是否开启从临床对话自动沉淀知识。",
    "KNOWLEDGE_AUTO_MAX_NEW_PER_TURN": "每轮对话最多自动新增的知识条数。",
    "KNOWLEDGE_AUTO_MIN_TEXT_CHARS": "触发自动沉淀时，医生输入的最小长度阈值。",
    "WECOM_CORP_ID": "企业微信企业ID（ww开头），在「我的企业 → 企业信息」中查看。",
    "WECOM_AGENT_ID": "自建应用的AgentID，在「应用管理」中查看。",
    "WECOM_SECRET": "自建应用的Secret，在「应用管理」中查看。",
    "WECHAT_TOKEN": "回调验证Token，在应用回调配置中自行设置。",
    "WECHAT_AES_KEY": "回调加密密钥（43位），在应用回调配置中随机生成。",
    "NOTIFICATION_PROVIDER": "通知后端（log 或 wechat）。",
    "WECHAT_NOTIFY_FALLBACK_TO_USER": "主接收人失败时的兜底 external_userid。",
    "WECHAT_MINI_APP_ID": "code2session 使用的小程序 appid。",
    "WECHAT_MINI_APP_SECRET": "code2session 使用的小程序密钥。",
    "MINIPROGRAM_TOKEN_SECRET": "小程序访问令牌签名密钥。",
    "MINIPROGRAM_TOKEN_TTL_SECONDS": "小程序访问令牌有效期（秒）。",
    "MINIPROGRAM_API_BASE_URL": "小程序客户端使用的公网 HTTPS API 基地址。",
    "UI_ADMIN_TOKEN": "Admin UI 端点所需的令牌（X-Admin-Token 请求头）。",
    "UI_DEBUG_TOKEN": "Debug UI 端点所需的令牌（X-Debug-Token 请求头），用于访问 /debug 页面（指标、可观测性、日志）。",
    "LOG_LEVEL": "根日志级别。",
    "LOG_FORMAT": "Python 日志格式字符串。",
    "LOG_TO_FILE": "是否启用文件滚动日志。",
    "LOG_DIR": "日志目录。",
    "LOG_FILE": "主日志文件名。",
    "LOG_MAX_BYTES": "单文件最大字节数，超过后滚动。",
    "LOG_BACKUP_COUNT": "日志备份保留数量。",
}

CONFIG_ALLOWED_VALUES: Dict[str, list[str]] = {
    "ROUTING_LLM": ["ollama", "deepseek", "groq", "gemini", "openai", "tencent_lkeap"],
    "STRUCTURING_LLM": ["ollama", "deepseek", "groq", "gemini", "openai", "tencent_lkeap"],
    "INTENT_PROVIDER": ["local", "model-driven"],
    "LLM_PROVIDER_STRICT_MODE": ["true", "false"],
    "KNOWLEDGE_AUTO_LEARN_ENABLED": ["true", "false"],
    "AGENT_ROUTING_PROMPT_MODE": ["full", "compact"],
    "AGENT_TOOL_SCHEMA_MODE": ["full", "compact"],
    "VISION_LLM": ["ollama", "gemini", "openai"],
    "WHISPER_DEVICE": ["cpu", "cuda"],
    "TASK_SCHEDULER_MODE": ["interval", "cron"],
    "NOTIFICATION_PROVIDER": ["log", "wechat"],
    "LOG_LEVEL": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
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
        from services.wechat.wechat_notify import _token_cache

        _token_cache["token"] = ""
        _token_cache["expires_at"] = 0.0
    except Exception:
        pass

    try:
        from services.ai import structuring as structuring_mod

        structuring_mod._PROMPT_CACHE = None
    except Exception:
        pass

    try:
        from services.ai import neuro_structuring as neuro_mod

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
