"""Egress policy gate — verifies the local / in-China / cross-border tiers."""
from __future__ import annotations

import pytest

from infra.llm.egress import (
    check_cloud_egress,
    is_cross_border_provider,
    is_in_china_provider,
    is_local_provider,
)


def test_local_providers_classified() -> None:
    for p in ("ollama", "local", "lmstudio"):
        assert is_local_provider(p)
        assert not is_in_china_provider(p)
        assert not is_cross_border_provider(p)


def test_in_china_providers_classified() -> None:
    for p in ("tencent_lkeap", "siliconflow", "dashscope", "deepseek"):
        assert is_in_china_provider(p)
        assert not is_local_provider(p)
        assert not is_cross_border_provider(p)


def test_cross_border_providers_classified() -> None:
    for p in ("groq", "openai", "gemini", "anthropic", "cerebras"):
        assert is_cross_border_provider(p)
        assert not is_local_provider(p)
        assert not is_in_china_provider(p)


def test_unknown_provider_treated_as_cross_border_fail_safe() -> None:
    assert is_cross_border_provider("brand_new_provider_2099")


def test_check_blocks_when_cloud_flag_unset(monkeypatch) -> None:
    monkeypatch.delenv("PHI_CLOUD_EGRESS_ALLOWED", raising=False)
    with pytest.raises(RuntimeError, match="Cloud egress blocked"):
        check_cloud_egress("siliconflow", "structuring")


def test_check_allows_in_china_with_only_cloud_flag(monkeypatch) -> None:
    monkeypatch.setenv("PHI_CLOUD_EGRESS_ALLOWED", "true")
    monkeypatch.delenv("PHI_CROSS_BORDER_ALLOWED", raising=False)
    # Should NOT raise — in-China provider, only cloud flag needed.
    check_cloud_egress("tencent_lkeap", "structuring")


def test_check_blocks_cross_border_when_only_cloud_flag(monkeypatch) -> None:
    monkeypatch.setenv("PHI_CLOUD_EGRESS_ALLOWED", "true")
    monkeypatch.delenv("PHI_CROSS_BORDER_ALLOWED", raising=False)
    with pytest.raises(RuntimeError, match="Cross-border egress blocked"):
        check_cloud_egress("groq", "vision_ocr")


def test_check_allows_cross_border_when_both_flags(monkeypatch) -> None:
    monkeypatch.setenv("PHI_CLOUD_EGRESS_ALLOWED", "true")
    monkeypatch.setenv("PHI_CROSS_BORDER_ALLOWED", "true")
    check_cloud_egress("groq", "vision_ocr")


def test_original_error_propagates_on_block(monkeypatch) -> None:
    """When original_error is provided, it's raised instead of RuntimeError."""
    monkeypatch.delenv("PHI_CLOUD_EGRESS_ALLOWED", raising=False)
    sentinel = ConnectionError("local LLM down")
    with pytest.raises(ConnectionError, match="local LLM down"):
        check_cloud_egress("groq", "vision_ocr", original_error=sentinel)
