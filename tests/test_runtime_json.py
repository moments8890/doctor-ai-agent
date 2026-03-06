from __future__ import annotations

from utils.runtime_json import CONFIG_ALLOWED_VALUES, DEFAULT_RUNTIME_CONFIG


def test_runtime_config_allows_tencent_lkeap_provider():
    assert "tencent_lkeap" in CONFIG_ALLOWED_VALUES["ROUTING_LLM"]
    assert "tencent_lkeap" in CONFIG_ALLOWED_VALUES["STRUCTURING_LLM"]


def test_runtime_config_has_tencent_lkeap_defaults():
    assert DEFAULT_RUNTIME_CONFIG["TENCENT_LKEAP_BASE_URL"] == "https://api.lkeap.cloud.tencent.com/v1"
    assert DEFAULT_RUNTIME_CONFIG["TENCENT_LKEAP_MODEL"] == "deepseek-v3-1"
    assert DEFAULT_RUNTIME_CONFIG["TENCENT_LKEAP_API_KEY"] == ""
