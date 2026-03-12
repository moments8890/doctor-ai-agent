"""Tests for runtime config validation, sanitization, and Alembic migration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from utils.runtime_config import (
    apply_runtime_config,
    runtime_config_categories,
    validate_runtime_config,
    _sanitize_config,
    DEFAULT_RUNTIME_CONFIG,
)


# ---------------------------------------------------------------------------
# runtime_config_categories structure
# ---------------------------------------------------------------------------

def test_runtime_config_categories_returns_structured_catalog():
    """runtime_config_categories must return a list of category dicts with items."""
    categories = runtime_config_categories({"ROUTING_LLM": "ollama"})
    assert isinstance(categories, list)
    assert len(categories) > 0
    for cat in categories:
        assert "items" in cat or "label" in cat


# ---------------------------------------------------------------------------
# apply_runtime_config sets env vars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_apply_runtime_config_sets_env_vars():
    """apply_runtime_config must set all keys into os.environ."""
    config = {"ROUTING_LLM": "deepseek", "LOG_LEVEL": "DEBUG"}
    import os
    with patch.dict("os.environ", {}, clear=True):
        await apply_runtime_config(config)
        assert os.environ.get("ROUTING_LLM") == "deepseek"
        assert os.environ.get("LOG_LEVEL") == "DEBUG"


# ---------------------------------------------------------------------------
# Enum config validation
# ---------------------------------------------------------------------------

def test_validate_rejects_invalid_enum_value():
    """validate_runtime_config must report ok=False for unsupported enum values."""
    result = validate_runtime_config({"ROUTING_LLM": "nonexistent_provider"})
    assert result["ok"] is False
    assert any("ROUTING_LLM" in err for err in result["errors"])


def test_validate_accepts_valid_enum_value():
    """Valid enum values should not produce errors."""
    result = validate_runtime_config({"ROUTING_LLM": "ollama"})
    key_errors = [e for e in result["errors"] if "ROUTING_LLM" in e]
    assert key_errors == []


def test_validate_rejects_invalid_log_level():
    """LOG_LEVEL with unsupported value triggers error."""
    result = validate_runtime_config({"LOG_LEVEL": "TRACE"})
    assert result["ok"] is False
    assert any("LOG_LEVEL" in err for err in result["errors"])


# ---------------------------------------------------------------------------
# Scheduler / knowledge integer field validation
# ---------------------------------------------------------------------------

def test_validate_rejects_non_integer_knowledge_key():
    """validate_runtime_config must report ok=False for non-integer knowledge values."""
    result = validate_runtime_config({"KNOWLEDGE_MAX_ITEMS": "abc"})
    assert result["ok"] is False
    assert any("KNOWLEDGE_MAX_ITEMS" in err for err in result["errors"])


def test_validate_accepts_valid_integer_knowledge_key():
    """Valid integers should not produce errors for knowledge keys."""
    result = validate_runtime_config({"KNOWLEDGE_MAX_ITEMS": 5})
    key_errors = [e for e in result["errors"] if "KNOWLEDGE_MAX_ITEMS" in e]
    assert key_errors == []


def test_validate_rejects_non_integer_lease_ttl():
    """Non-integer TASK_SCHEDULER_LEASE_TTL_SECONDS triggers error."""
    result = validate_runtime_config({"TASK_SCHEDULER_LEASE_TTL_SECONDS": "abc"})
    assert result["ok"] is False
    assert any("TASK_SCHEDULER_LEASE_TTL_SECONDS" in err for err in result["errors"])


def test_validate_warns_low_lease_ttl():
    """Lease TTL below 10 produces a warning."""
    result = validate_runtime_config({"TASK_SCHEDULER_LEASE_TTL_SECONDS": 5})
    assert any("TASK_SCHEDULER_LEASE_TTL_SECONDS" in w for w in result["warnings"])


def test_validate_rejects_bad_cron_in_cron_mode():
    """Invalid cron expression when mode=cron triggers error."""
    result = validate_runtime_config({
        "TASK_SCHEDULER_MODE": "cron",
        "TASK_SCHEDULER_CRON": "bad cron",
    })
    assert result["ok"] is False
    assert any("TASK_SCHEDULER_CRON" in err for err in result["errors"])


# ---------------------------------------------------------------------------
# Sanitize config
# ---------------------------------------------------------------------------

def test_sanitize_clamps_invalid_knowledge_to_default():
    """Sanitization must replace unparseable knowledge values with safe defaults."""
    result = _sanitize_config({"KNOWLEDGE_MAX_ITEMS": "NaN"})
    assert result["KNOWLEDGE_MAX_ITEMS"] == str(DEFAULT_RUNTIME_CONFIG["KNOWLEDGE_MAX_ITEMS"])


def test_sanitize_clamps_knowledge_below_minimum():
    """Knowledge values below the minimum floor must be clamped up."""
    result = _sanitize_config({"KNOWLEDGE_MAX_ITEMS": "-5"})
    assert int(result["KNOWLEDGE_MAX_ITEMS"]) >= 1


def test_sanitize_normalizes_scheduler_mode():
    """Invalid scheduler mode falls back to 'interval'."""
    result = _sanitize_config({"TASK_SCHEDULER_MODE": "invalid"})
    assert result["TASK_SCHEDULER_MODE"] == "interval"


def test_sanitize_normalizes_log_level():
    """Invalid LOG_LEVEL falls back to 'INFO'."""
    result = _sanitize_config({"LOG_LEVEL": "TRACE"})
    assert result["LOG_LEVEL"] == "INFO"


# ---------------------------------------------------------------------------
# Alembic migration resilience
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_alembic_migration_failure_tolerated():
    """Migration failure must be caught and logged, not re-raised."""
    with patch("alembic.command.upgrade", side_effect=RuntimeError("migration failed")), \
         patch("alembic.config.Config"):
        from main import _run_alembic_migrations

        # Should NOT raise — function catches all exceptions
        await _run_alembic_migrations()


@pytest.mark.asyncio
async def test_alembic_migration_success():
    """Successful migration path should complete without error."""
    with patch("alembic.command.upgrade") as mock_upgrade, \
         patch("alembic.config.Config"):
        from main import _run_alembic_migrations

        await _run_alembic_migrations()
        mock_upgrade.assert_called_once()
