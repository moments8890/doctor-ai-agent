"""Pure metadata dicts for runtime config — categories, descriptions, allowed values.

No side effects, no os.environ reads, no file I/O.
Imported by runtime_config.py; must NOT import from runtime_config.py.
"""
from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Category definitions — which config keys belong to each group
# ---------------------------------------------------------------------------

CONFIG_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "llm": {
        "description": "LLM provider routing and model selection.",
        "keys": [
            "ROUTING_LLM",
            "STRUCTURING_LLM",
            "DIAGNOSIS_LLM",
            "LLM_PROVIDER_STRICT_MODE",
            "VISION_LLM",
            "OPENAI_API_KEY",
            "TENCENT_LKEAP_BASE_URL",
            "TENCENT_LKEAP_MODEL",
            "TENCENT_LKEAP_API_KEY",
            "GROQ_API_KEY",
            "DEEPSEEK_API_KEY",
            "CEREBRAS_API_KEY",
            "SAMBANOVA_API_KEY",
            "SILICONFLOW_API_KEY",
            "OPENROUTER_API_KEY",
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
            "PENDING_RECORD_TTL_MINUTES",
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
        "description": "Tokens for the admin and debug web UIs, and patient portal secret.",
        "description_zh": "Admin/Debug Web UI 访问令牌及患者门户签名密钥。",
        "keys": [
            "UI_ADMIN_TOKEN",
            "UI_DEBUG_TOKEN",
            "PATIENT_PORTAL_SECRET",
            "PHI_CLOUD_EGRESS_ALLOWED",
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
    "embedding": {
        "description": "Embedding model for case history RAG matching.",
        "keys": [
            "EMBEDDING_PROVIDER",
            "EMBEDDING_MODEL",
            "EMBEDDING_PRELOAD",
            "DASHSCOPE_API_KEY",
            "SKILLS_CACHE_TTL",
        ],
    },
}

# ---------------------------------------------------------------------------
# Category-level Chinese descriptions
# ---------------------------------------------------------------------------

CATEGORY_DESCRIPTIONS_ZH: Dict[str, str] = {
    "llm": "LLM 提供商路由与模型选择。",
    "storage": "数据库与存储路径配置。",
    "automation": "临床自动化与调度行为。",
    "wecom": "企业微信自建应用集成与通知配置。",
    "miniprogram": "微信小程序鉴权与端点默认配置。",
    "logging": "应用日志与滚动策略。",
    "embedding": "病历 RAG 匹配的嵌入模型。",
}

# ---------------------------------------------------------------------------
# Per-key English descriptions
# ---------------------------------------------------------------------------

CONFIG_DESCRIPTIONS: Dict[str, str] = {
    "ROUTING_LLM": "Provider for intent/tool routing. Note: Ollama is LAN/local LLM (can be slower); DeepSeek is online LLM (billed).",
    "STRUCTURING_LLM": "Provider for medical record structuring. Note: Ollama is LAN/local LLM (can be slower); DeepSeek is online LLM (billed).",
    "DIAGNOSIS_LLM": "LLM provider for diagnosis pipeline. Falls back to STRUCTURING_LLM if empty.",
    "LLM_PROVIDER_STRICT_MODE": "When true, use selected provider only and never fallback to others.",
    "VISION_LLM": "Provider for image understanding.",
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
    "PATIENT_PORTAL_SECRET": "JWT signing secret for the patient portal. MUST be set in production; defaults to a dev value otherwise.",
    "LOG_LEVEL": "Root logging level.",
    "LOG_FORMAT": "Python logging formatter string.",
    "LOG_TO_FILE": "Enable rotating file logging.",
    "LOG_DIR": "Directory for log files.",
    "LOG_FILE": "Primary app log filename.",
    "LOG_MAX_BYTES": "Max bytes per log file before rotation.",
    "LOG_BACKUP_COUNT": "Number of rotated log backups to keep.",
    "EMBEDDING_PROVIDER": "Embedding provider: 'local' (BGE-M3 via sentence-transformers) or 'dashscope' (Alibaba Cloud).",
    "EMBEDDING_MODEL": "Model name for local embedding provider (default: BAAI/bge-m3).",
    "EMBEDDING_PRELOAD": "Preload embedding model at app startup (default: true).",
    "DASHSCOPE_API_KEY": "API key for Dashscope embedding provider (only if EMBEDDING_PROVIDER=dashscope).",
    "SKILLS_CACHE_TTL": "Skill file cache TTL in seconds (default: 300 = 5 minutes).",
}

# ---------------------------------------------------------------------------
# Per-key Chinese descriptions
# ---------------------------------------------------------------------------

CONFIG_DESCRIPTIONS_ZH: Dict[str, str] = {
    "ROUTING_LLM": "意图/工具路由使用的提供商。说明：Ollama 通常是局域网/本地 LLM（可能较慢）；DeepSeek 是在线 LLM（按量计费）。",
    "STRUCTURING_LLM": "病历结构化使用的提供商。说明：Ollama 通常是局域网/本地 LLM（可能较慢）；DeepSeek 是在线 LLM（按量计费）。",
    "DIAGNOSIS_LLM": "诊断管道使用的LLM提供商。为空时使用STRUCTURING_LLM。",
    "LLM_PROVIDER_STRICT_MODE": "为 true 时仅使用所选提供商，不会自动回退到其它提供商。",
    "VISION_LLM": "图像理解使用的提供商。",
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
    "PATIENT_PORTAL_SECRET": "患者门户 JWT 签名密钥，生产环境必须设置，否则使用开发默认值。",
    "LOG_LEVEL": "根日志级别。",
    "LOG_FORMAT": "Python 日志格式字符串。",
    "LOG_TO_FILE": "是否启用文件滚动日志。",
    "LOG_DIR": "日志目录。",
    "LOG_FILE": "主日志文件名。",
    "LOG_MAX_BYTES": "单文件最大字节数，超过后滚动。",
    "LOG_BACKUP_COUNT": "日志备份保留数量。",
    "EMBEDDING_PROVIDER": "嵌入模型提供商：'local'（本地 BGE-M3）或 'dashscope'（阿里云）。",
    "EMBEDDING_MODEL": "本地嵌入模型名称（默认：BAAI/bge-m3）。",
    "EMBEDDING_PRELOAD": "启动时预加载嵌入模型（默认：true）。",
    "DASHSCOPE_API_KEY": "Dashscope 嵌入提供商 API 密钥。",
    "SKILLS_CACHE_TTL": "技能文件缓存 TTL（秒，默认 300 = 5 分钟）。",
}

# ---------------------------------------------------------------------------
# Allowed values for enum/select fields
# ---------------------------------------------------------------------------

CONFIG_ALLOWED_VALUES: Dict[str, List[str]] = {
    "ROUTING_LLM": ["deepseek", "groq", "cerebras", "sambanova", "siliconflow", "openrouter", "tencent_lkeap", "ollama"],
    "STRUCTURING_LLM": ["deepseek", "groq", "cerebras", "sambanova", "siliconflow", "openrouter", "tencent_lkeap", "ollama"],
    "LLM_PROVIDER_STRICT_MODE": ["true", "false"],
    "KNOWLEDGE_AUTO_LEARN_ENABLED": ["true", "false"],
    "VISION_LLM": ["ollama", "gemini", "openai"],
    "TASK_SCHEDULER_MODE": ["interval", "cron"],
    "NOTIFICATION_PROVIDER": ["log", "wechat"],
    "LOG_LEVEL": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
}
