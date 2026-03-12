"""Tests for services.hooks_builtin — built-in hook registrations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.hooks import HookStage, clear_hooks, list_hooks


@pytest.fixture(autouse=True)
def _clean_hooks():
    """Ensure hooks are cleared before and after every test."""
    clear_hooks()
    yield
    clear_hooks()


# ---------- Registration on import ----------


def test_import_registers_post_classify_and_post_gate():
    """Importing hooks_builtin should register hooks for POST_CLASSIFY and POST_GATE."""
    import importlib
    import services.hooks_builtin  # noqa: F811
    importlib.reload(services.hooks_builtin)

    info = list_hooks()
    assert info["post_classify"] >= 1
    assert info["post_gate"] >= 1


# ---------- _log_classification ----------


def test_log_classification_extracts_intent_and_source():
    """_log_classification should extract intent/source from the decision object."""
    from services.hooks_builtin import _log_classification

    decision = MagicMock()
    decision.intent = "add_record"
    decision.source = "fast_route"

    ctx = {
        "decision": decision,
        "doctor_id": "d1",
        "latency_ms": 42.5,
    }

    with patch("services.hooks_builtin.log") as mock_log:
        _log_classification(ctx)

    mock_log.assert_called_once()
    call_str = mock_log.call_args[0][0]
    assert "add_record" in call_str
    assert "fast_route" in call_str
    assert "d1" in call_str
    assert "43ms" in call_str or "42ms" in call_str


def test_log_classification_handles_missing_decision():
    """_log_classification should handle ctx with no decision gracefully."""
    from services.hooks_builtin import _log_classification

    ctx = {"doctor_id": "d2"}

    with patch("services.hooks_builtin.log") as mock_log:
        _log_classification(ctx)

    mock_log.assert_called_once()
    call_str = mock_log.call_args[0][0]
    assert "intent=?" in call_str
    assert "source=?" in call_str


def test_log_classification_handles_none_latency():
    """_log_classification should omit latency string when latency_ms is None."""
    from services.hooks_builtin import _log_classification

    decision = MagicMock()
    decision.intent = "query_records"
    decision.source = "llm"

    ctx = {"decision": decision, "doctor_id": "d3", "latency_ms": None}

    with patch("services.hooks_builtin.log") as mock_log:
        _log_classification(ctx)

    call_str = mock_log.call_args[0][0]
    assert "query_records" in call_str
    # No latency should be present when it's None
    assert "ms" not in call_str.split("source=")[1]


# ---------- _log_gate ----------


def test_log_gate_logs_when_gate_not_approved():
    """_log_gate should log when gate.approved is False."""
    from services.hooks_builtin import _log_gate

    gate = MagicMock()
    gate.approved = False
    gate.reason = "no_patient"

    decision = MagicMock()
    decision.intent = "add_record"

    ctx = {"gate": gate, "decision": decision, "doctor_id": "d1"}

    with patch("services.hooks_builtin.log") as mock_log:
        _log_gate(ctx)

    mock_log.assert_called_once()
    call_str = mock_log.call_args[0][0]
    assert "BLOCKED" in call_str
    assert "no_patient" in call_str
    assert "add_record" in call_str


def test_log_gate_silent_when_gate_approved():
    """_log_gate should NOT log when gate.approved is True."""
    from services.hooks_builtin import _log_gate

    gate = MagicMock()
    gate.approved = True
    gate.reason = ""

    ctx = {"gate": gate, "decision": MagicMock(), "doctor_id": "d1"}

    with patch("services.hooks_builtin.log") as mock_log:
        _log_gate(ctx)

    mock_log.assert_not_called()


def test_log_gate_silent_when_no_gate_in_ctx():
    """_log_gate should NOT log when gate key is missing from ctx."""
    from services.hooks_builtin import _log_gate

    ctx = {"doctor_id": "d1"}

    with patch("services.hooks_builtin.log") as mock_log:
        _log_gate(ctx)

    mock_log.assert_not_called()


def test_log_gate_silent_when_gate_is_none():
    """_log_gate should NOT log when gate is None (defaults to approved=True)."""
    from services.hooks_builtin import _log_gate

    ctx = {"gate": None, "doctor_id": "d1"}

    with patch("services.hooks_builtin.log") as mock_log:
        _log_gate(ctx)

    mock_log.assert_not_called()
