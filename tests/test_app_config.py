from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from utils.app_config import AppConfig, load_config_from_json


def test_load_config_from_json_uses_runtime_loader():
    with patch("utils.app_config.runtime_config_path", return_value=Path("/tmp/runtime.json")), \
         patch("utils.app_config.load_runtime_json", return_value={"ROUTING_LLM": "ollama"}):
        source, values = load_config_from_json("/tmp/runtime.json")

    assert source == Path("/tmp/runtime.json")
    assert values["ROUTING_LLM"] == "ollama"


def test_app_config_reads_env_and_masks_sensitive_fields():
    env = {
        "ROUTING_LLM": "ollama",
        "STRUCTURING_LLM": "ollama",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1",
        "OLLAMA_MODEL": "qwen2.5:14b",
        "OLLAMA_API_KEY": "ollama-secret-key",
        "DEEPSEEK_API_KEY": "deepseek-secret",
        "GROQ_API_KEY": "groq-secret",
        "GEMINI_API_KEY": "gemini-secret",
        "WECHAT_TOKEN": "wechat-token",
        "WECHAT_APP_ID": "wx12345",
        "WECHAT_APP_SECRET": "wechat-app-secret",
        "WECHAT_ENCODING_AES_KEY": "wechat-aes-secret",
        "AUTO_FOLLOWUP_TASKS_ENABLED": "true",
        "LOG_TO_FILE": "false",
        "LOG_MAX_BYTES": "2048",
        "LOG_BACKUP_COUNT": "8",
    }
    config = AppConfig.from_env(env, env_source="/tmp/shared.env")
    fields = config.to_log_fields()

    assert config.env_source == "/tmp/shared.env"
    assert config.ollama_model == "qwen2.5:14b"
    assert config.auto_followup_tasks_enabled is True
    assert config.log_to_file is False
    assert config.log_max_bytes == 2048
    assert config.log_backup_count == 8
    assert fields["ollama_api_key"].startswith("ol***")
    assert fields["wechat_token"] == "we***en"
    assert fields["wechat_app_id"] == "wx12345"


def test_app_config_defaults_are_stable():
    config = AppConfig.from_env({}, env_source=".env")
    fields = config.to_log_fields()

    assert config.routing_llm == "deepseek"
    assert config.structuring_llm == "deepseek"
    assert config.ollama_model == "qwen2.5:14b"
    assert config.ollama_vision_model == "qwen2.5vl:7b"
    assert config.whisper_model == "large-v3"
    assert config.log_to_file is True
    assert fields["patients_db_path"] == "(default)"
    assert fields["ollama_api_key"] == "***"


def test_app_config_prefers_wechat_kf_env_keys():
    env = {
        "WECHAT_KF_TOKEN": "kf-token",
        "WECHAT_KF_CORP_ID": "ww-corp-id",
        "WECHAT_KF_SECRET": "kf-secret",
        "WECHAT_KF_ENCODING_AES_KEY": "kf-aes",
        "WECHAT_TOKEN": "legacy-token",
        "WECHAT_APP_ID": "legacy-app-id",
        "WECHAT_APP_SECRET": "legacy-secret",
        "WECHAT_ENCODING_AES_KEY": "legacy-aes",
    }
    config = AppConfig.from_env(env, env_source=".env")

    assert config.wechat_token == "kf-token"
    assert config.wechat_app_id == "ww-corp-id"
    assert config.wechat_app_secret == "kf-secret"
    assert config.wechat_encoding_aes_key == "kf-aes"


def test_app_config_pretty_log_is_multiline_and_aligned():
    config = AppConfig.from_env(
        {"ROUTING_LLM": "ollama", "OLLAMA_MODEL": "qwen2.5:14b"},
        env_source=".env",
    )
    pretty = config.to_pretty_log()

    assert "\n" in pretty
    assert "routing_llm" in pretty
    assert "ollama_model" in pretty
    assert " : " in pretty
