"""Tests for the always-on signal-flag classifier.

The classifier runs on every patient turn regardless of conversational
state — a routine question and a signal-flag message in the same turn must
both fire, so detect() takes only (message, patient_context) and never
a session/state argument.
"""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_obvious_emergency_returns_true():
    from domain.patient_lifecycle.signal_flag import detect
    with patch(
        "domain.patient_lifecycle.signal_flag._classify_urgent",
        AsyncMock(return_value=True),
    ):
        result = await detect("我现在胸口剧痛喘不上气", patient_context={})
    assert result is True


@pytest.mark.asyncio
async def test_routine_question_returns_false():
    from domain.patient_lifecycle.signal_flag import detect
    with patch(
        "domain.patient_lifecycle.signal_flag._classify_urgent",
        AsyncMock(return_value=False),
    ):
        result = await detect("怎么改预约时间", patient_context={})
    assert result is False


@pytest.mark.asyncio
async def test_runs_independently_of_state():
    """detect() must not require any session/state argument."""
    import inspect

    from domain.patient_lifecycle.signal_flag import detect

    sig = inspect.signature(detect)
    assert "session" not in sig.parameters, (
        "signal_flag.detect must not depend on session — it's a per-turn classifier"
    )
    assert "state" not in sig.parameters, (
        "signal_flag.detect must not depend on conversational state"
    )
