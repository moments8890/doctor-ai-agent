"""Tests for services/patient/prior_visit.py."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.patient.prior_visit import _format_cvd_summary, get_prior_visit_summary


# ---------------------------------------------------------------------------
# _format_cvd_summary unit tests (pure, no DB)
# ---------------------------------------------------------------------------

def test_format_cvd_summary_with_ich_score():
    raw = json.dumps({"ich_score": 4, "gcs_score": 10, "surgery_status": "术后"})
    result = _format_cvd_summary(raw, "2026-03-01")
    assert result is not None
    assert "ICH Score=4" in result
    assert "GCS=10" in result
    assert "手术状态=术后" in result
    assert "2026-03-01" in result


def test_format_cvd_summary_with_hunt_hess():
    raw = json.dumps({"hunt_hess_grade": 3, "fisher_grade": 2, "diagnosis_subtype": "SAH"})
    result = _format_cvd_summary(raw, None)
    assert result is not None
    assert "Hunt-Hess=3" in result
    assert "Fisher=2" in result
    assert "病种=SAH" in result
    # No date in result
    assert "（" not in result or "（None）" not in result


def test_format_cvd_summary_no_known_fields():
    raw = json.dumps({"unknown_field": 99})
    result = _format_cvd_summary(raw, "2026-01-01")
    assert result is None


def test_format_cvd_summary_empty_json():
    result = _format_cvd_summary("{}", "2026-01-01")
    assert result is None


def test_format_cvd_summary_invalid_json():
    result = _format_cvd_summary("not-json", "2026-01-01")
    assert result is None


def test_format_cvd_summary_none_input():
    result = _format_cvd_summary(None, "2026-01-01")
    assert result is None


# ---------------------------------------------------------------------------
# get_prior_visit_summary integration tests (DB mocked)
# ---------------------------------------------------------------------------

def _make_cvd_row(raw_json: str, created_at=None):
    from datetime import datetime
    row = MagicMock()
    row.raw_json = raw_json
    row.created_at = created_at or datetime(2026, 2, 1, 10, 0, 0)
    return row


def _make_record_row(content: str, created_at=None):
    from datetime import datetime
    row = MagicMock()
    row.content = content
    row.created_at = created_at or datetime(2026, 2, 1, 10, 0, 0)
    return row


@pytest.fixture
def mock_db_session(monkeypatch):
    """Patch AsyncSessionLocal so queries return controllable data."""
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "services.patient.prior_visit.AsyncSessionLocal",
        MagicMock(return_value=ctx),
    )
    return session


@pytest.mark.asyncio
async def test_get_prior_visit_summary_cvd_row(mock_db_session):
    cvd_row = _make_cvd_row(json.dumps({"ich_score": 5, "gcs_score": 8}))
    # First execute → CVD context result
    cvd_result = MagicMock()
    cvd_result.scalar_one_or_none = MagicMock(return_value=cvd_row)
    mock_db_session.execute = AsyncMock(return_value=cvd_result)

    summary = await get_prior_visit_summary("doc1", 42)
    assert summary is not None
    assert "ICH Score=5" in summary
    assert "GCS=8" in summary


@pytest.mark.asyncio
async def test_get_prior_visit_summary_falls_back_to_record(mock_db_session):
    # No CVD row, then a record row
    no_cvd = MagicMock()
    no_cvd.scalar_one_or_none = MagicMock(return_value=None)
    rec_row = _make_record_row("患者血压控制良好，继续氨氯地平。")
    rec_result = MagicMock()
    rec_result.scalar_one_or_none = MagicMock(return_value=rec_row)

    mock_db_session.execute = AsyncMock(side_effect=[no_cvd, rec_result])

    summary = await get_prior_visit_summary("doc1", 42)
    assert summary is not None
    assert "患者血压控制良好" in summary
    assert "上次就诊" in summary


@pytest.mark.asyncio
async def test_get_prior_visit_summary_no_data(mock_db_session):
    empty = MagicMock()
    empty.scalar_one_or_none = MagicMock(return_value=None)
    mock_db_session.execute = AsyncMock(return_value=empty)

    summary = await get_prior_visit_summary("doc1", 42)
    assert summary is None


@pytest.mark.asyncio
async def test_get_prior_visit_summary_db_error(mock_db_session):
    mock_db_session.execute = AsyncMock(side_effect=Exception("DB unavailable"))
    summary = await get_prior_visit_summary("doc1", 42)
    assert summary is None


# ---------------------------------------------------------------------------
# structure_medical_record: prior_visit_summary injected into user message
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_structure_medical_record_injects_prior_summary(monkeypatch):
    """prior_visit_summary should be prepended to the user message sent to LLM."""
    import json as _json
    from services.ai.structuring import structure_medical_record

    captured_messages = []

    async def _fake_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        msg = MagicMock()
        msg.content = _json.dumps({"content": "复诊记录", "tags": []})
        choice = MagicMock()
        choice.message = msg
        result = MagicMock()
        result.choices = [choice]
        return result

    monkeypatch.setenv("STRUCTURING_LLM", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER_STRICT_MODE", "false")

    async def _mock_retry(fn, **kw):
        return await fn(kw.get("primary_model", "x"))

    with patch("services.ai.structuring.call_with_retry_and_fallback", new=_mock_retry):
        with patch("services.ai.structuring._get_structuring_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create = _fake_create
            mock_client_fn.return_value = mock_client
            with patch("services.ai.structuring._get_system_prompt", new=AsyncMock(return_value="sys")):
                await structure_medical_record(
                    "本次血压120/80，继续原方案",
                    encounter_type="follow_up",
                    prior_visit_summary="ICH Score=4，GCS=10",
                )

    user_msg = next(m for m in captured_messages if m["role"] == "user")
    assert "【上次就诊参考】" in user_msg["content"]
    assert "ICH Score=4" in user_msg["content"]
    assert "【本次记录】" in user_msg["content"]
    assert "本次血压120/80" in user_msg["content"]


@pytest.mark.asyncio
async def test_structure_medical_record_no_prior_summary_unchanged(monkeypatch):
    """Without prior_visit_summary, user message is the plain text."""
    import json as _json
    from services.ai.structuring import structure_medical_record

    captured_messages = []

    async def _fake_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        msg = MagicMock()
        msg.content = _json.dumps({"content": "普通记录", "tags": []})
        choice = MagicMock()
        choice.message = msg
        result = MagicMock()
        result.choices = [choice]
        return result

    monkeypatch.setenv("STRUCTURING_LLM", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER_STRICT_MODE", "false")

    async def _mock_retry(fn, **kw):
        return await fn(kw.get("primary_model", "x"))

    with patch("services.ai.structuring.call_with_retry_and_fallback", new=_mock_retry):
        with patch("services.ai.structuring._get_structuring_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create = _fake_create
            mock_client_fn.return_value = mock_client
            with patch("services.ai.structuring._get_system_prompt", new=AsyncMock(return_value="sys")):
                await structure_medical_record("初诊记录")

    user_msg = next(m for m in captured_messages if m["role"] == "user")
    assert user_msg["content"] == "初诊记录"
    assert "【上次就诊参考】" not in user_msg["content"]
