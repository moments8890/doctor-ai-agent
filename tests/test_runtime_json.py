"""运行时 JSON 配置测试：验证腾讯 LKE-AP 提供商的配置允许值及默认值是否正确注册。"""

from __future__ import annotations

from utils.runtime_config import CONFIG_ALLOWED_VALUES, DEFAULT_RUNTIME_CONFIG


def test_runtime_config_allows_tencent_lkeap_provider():
    assert "tencent_lkeap" in CONFIG_ALLOWED_VALUES["ROUTING_LLM"]
    assert "tencent_lkeap" in CONFIG_ALLOWED_VALUES["STRUCTURING_LLM"]


def test_runtime_config_has_tencent_lkeap_defaults():
    assert DEFAULT_RUNTIME_CONFIG["TENCENT_LKEAP_BASE_URL"] == "https://api.lkeap.cloud.tencent.com/v1"
    assert DEFAULT_RUNTIME_CONFIG["TENCENT_LKEAP_MODEL"] == "deepseek-v3-1"
    assert DEFAULT_RUNTIME_CONFIG["TENCENT_LKEAP_API_KEY"] == ""
