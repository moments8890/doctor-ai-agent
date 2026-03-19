"""应用配置加载：从环境变量或 runtime.json 构建 AppConfig 数据类。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from utils.runtime_config import load_runtime_json, runtime_config_path

_SENSITIVE_FIELD_NAMES = {
    "ollama_api_key",
    "deepseek_api_key",
    "groq_api_key",
    "gemini_api_key",
    "openai_api_key",
    "tencent_lkeap_api_key",
    "wechat_token",
    "wechat_app_secret",
    "wechat_mini_app_secret",
    "wechat_encoding_aes_key",
}


def _as_bool(raw: Optional[str], default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_flag_true(name: str, default: bool = False) -> bool:
    """Return True if the environment variable *name* is a truthy string.

    This is the canonical env-flag reader.  Recognised truthy values:
    ``1``, ``true``, ``yes``, ``on`` (case-insensitive).
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(raw: Optional[str], default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def _env_first(values: Mapping[str, str], *names: str) -> Optional[str]:
    for name in names:
        value = values.get(name)
        if value is not None and value.strip():
            return value
    return None


def _mask_secret(value: Optional[str]) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 6:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def parse_timeout(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


DEFAULT_TIMEOUT = parse_timeout("abc")
def _pretty_log_lines(fields: Mapping[str, str]) -> str:
    if not fields:
        return "(empty)"
    max_key_len = max(len(k) for k in fields.keys())
    lines = []
    for key in sorted(fields.keys()):
        lines.append(f"  {key.ljust(max_key_len)} : {fields[key]}")
    return "\n".join(lines)


def load_config_from_json(path: Optional[str] = None) -> tuple[Path, Dict[str, str]]:
    target = runtime_config_path(path)
    loaded = load_runtime_json(path)
    values = {k: str(v) for k, v in loaded.items()}
    return target, values


def ollama_base_url_candidates(primary_url: str) -> List[str]:
    """Return ordered unique Ollama base URL candidates.

    Always tries configured URL first, then localhost fallback.
    """
    fallback = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    out: List[str] = []
    for url in [primary_url.strip(), fallback]:
        if not url:
            continue
        if url not in out:
            out.append(url)
    return out


@dataclass(frozen=True)
class AppConfig:
    env_source: str
    routing_llm: str
    structuring_llm: str
    intent_provider: str
    llm_provider_strict_mode: bool
    vision_llm: str

    ollama_base_url: str
    ollama_vision_base_url: str
    ollama_model: str
    ollama_vision_model: str
    ollama_api_key: Optional[str]

    deepseek_api_key: Optional[str]
    groq_api_key: Optional[str]
    openai_api_key: Optional[str]
    tencent_lkeap_base_url: str
    tencent_lkeap_model: str
    tencent_lkeap_api_key: Optional[str]
    gemini_api_key: Optional[str]
    gemini_vision_model: str

    wechat_token: Optional[str]
    wechat_app_id: Optional[str]
    wechat_app_secret: Optional[str]
    wechat_mini_app_id: Optional[str]
    wechat_mini_app_secret: Optional[str]
    wechat_encoding_aes_key: Optional[str]

    patients_db_path: Optional[str]
    auto_followup_tasks_enabled: bool

    log_level: str
    log_format: str
    log_to_file: bool
    log_dir: str
    log_file: str
    log_max_bytes: int
    log_backup_count: int

    @classmethod
    def _llm_fields(cls, values: Mapping[str, str]) -> dict:
        """LLM 路由、模型和 API Key 字段。"""
        _ollama_default = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return dict(
            routing_llm=values.get("ROUTING_LLM", "deepseek"),
            structuring_llm=values.get("STRUCTURING_LLM", "deepseek"),
            intent_provider=values.get("INTENT_PROVIDER", "local"),
            llm_provider_strict_mode=_as_bool(values.get("LLM_PROVIDER_STRICT_MODE"), default=True),
            vision_llm=values.get("VISION_LLM", "ollama"),
            ollama_base_url=values.get("OLLAMA_BASE_URL", _ollama_default),
            ollama_vision_base_url=values.get("OLLAMA_VISION_BASE_URL", values.get("OLLAMA_BASE_URL", _ollama_default)),
            ollama_model=values.get("OLLAMA_MODEL", "qwen3.5:9b"),
            ollama_vision_model=values.get("OLLAMA_VISION_MODEL", "qwen3-vl:8b"),
            ollama_api_key=values.get("OLLAMA_API_KEY", "ollama"),
            deepseek_api_key=values.get("DEEPSEEK_API_KEY"),
            groq_api_key=values.get("GROQ_API_KEY"),
            openai_api_key=values.get("OPENAI_API_KEY"),
            tencent_lkeap_base_url=values.get("TENCENT_LKEAP_BASE_URL", "https://api.lkeap.cloud.tencent.com/v1"),
            tencent_lkeap_model=values.get("TENCENT_LKEAP_MODEL", "deepseek-v3-1"),
            tencent_lkeap_api_key=values.get("TENCENT_LKEAP_API_KEY"),
            gemini_api_key=values.get("GEMINI_API_KEY"),
            gemini_vision_model=values.get("GEMINI_VISION_MODEL", "gemini-2.0-flash"),
        )

    @classmethod
    def _wechat_and_infra_fields(cls, values: Mapping[str, str]) -> dict:
        """微信/企业微信凭证及基础设施（语音/日志）字段。"""
        return dict(
            wechat_token=_env_first(values, "WECHAT_KF_TOKEN", "WECHAT_TOKEN"),
            wechat_app_id=_env_first(values, "WECHAT_KF_CORP_ID", "WECHAT_APP_ID"),
            wechat_app_secret=_env_first(values, "WECHAT_KF_SECRET", "WECHAT_APP_SECRET"),
            wechat_mini_app_id=values.get("WECHAT_MINI_APP_ID"),
            wechat_mini_app_secret=values.get("WECHAT_MINI_APP_SECRET"),
            wechat_encoding_aes_key=_env_first(values, "WECHAT_KF_ENCODING_AES_KEY", "WECHAT_ENCODING_AES_KEY"),
            patients_db_path=values.get("PATIENTS_DB_PATH"),
            auto_followup_tasks_enabled=_as_bool(values.get("AUTO_FOLLOWUP_TASKS_ENABLED"), default=False),
            log_level=values.get("LOG_LEVEL", "INFO").upper(),
            log_format=values.get("LOG_FORMAT", "%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
            log_to_file=_as_bool(values.get("LOG_TO_FILE"), default=True),
            log_dir=values.get("LOG_DIR", "logs"),
            log_file=values.get("LOG_FILE", "app.log"),
            log_max_bytes=_as_int(values.get("LOG_MAX_BYTES"), default=10485760),
            log_backup_count=_as_int(values.get("LOG_BACKUP_COUNT"), default=5),
        )

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None, *, env_source: str) -> "AppConfig":
        """从环境变量映射（或 os.environ）构建 AppConfig 实例。"""
        values: Mapping[str, str] = env if env is not None else os.environ
        return cls(
            env_source=env_source,
            **cls._llm_fields(values),
            **cls._wechat_and_infra_fields(values),
        )

    def to_log_fields(self) -> Dict[str, str]:
        fields: Dict[str, str] = {
            "env_source": self.env_source,
            "routing_llm": self.routing_llm,
            "structuring_llm": self.structuring_llm,
            "intent_provider": self.intent_provider,
            "llm_provider_strict_mode": str(self.llm_provider_strict_mode).lower(),
            "vision_llm": self.vision_llm,
            "ollama_base_url": self.ollama_base_url,
            "ollama_vision_base_url": self.ollama_vision_base_url,
            "ollama_model": self.ollama_model,
            "ollama_vision_model": self.ollama_vision_model,
            "gemini_vision_model": self.gemini_vision_model,
            "tencent_lkeap_base_url": self.tencent_lkeap_base_url,
            "tencent_lkeap_model": self.tencent_lkeap_model,
            "wechat_app_id": self.wechat_app_id or "(empty)",
            "wechat_mini_app_id": self.wechat_mini_app_id or "(empty)",
            "patients_db_path": self.patients_db_path or "(default)",
            "auto_followup_tasks_enabled": str(self.auto_followup_tasks_enabled).lower(),
            "log_level": self.log_level,
            "log_to_file": str(self.log_to_file).lower(),
            "log_dir": self.log_dir,
            "log_file": self.log_file,
            "log_max_bytes": str(self.log_max_bytes),
            "log_backup_count": str(self.log_backup_count),
        }

        for field_name in _SENSITIVE_FIELD_NAMES:
            fields[field_name] = _mask_secret(getattr(self, field_name))
        return fields

    def to_pretty_log(self) -> str:
        return _pretty_log_lines(self.to_log_fields())
