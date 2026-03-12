"""Unit tests for services.domain.intent_handlers._query_records."""
from __future__ import annotations

import pytest
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai.intent import Intent, IntentResult
from services.domain.intent_handlers._types import HandlerResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOD = "services.domain.intent_handlers._query_records"


@contextmanager
def _noop_trace(*args, **kwargs):
    yield


def _intent(name: Optional[str] = None) -> IntentResult:
    return IntentResult(intent=Intent.query_records, patient_name=name)


def _patient(pid: int = 1, name: str = "张三"):
    return SimpleNamespace(id=pid, name=name)


def _record(content: str = "头痛三天", created_at: Optional[datetime] = None, patient_name: str = "张三"):
    dt = created_at or datetime(2026, 3, 10, 10, 0, 0)
    return SimpleNamespace(
        content=content,
        created_at=dt,
        patient=SimpleNamespace(name=patient_name),
    )


def _session(
    current_patient_id: Optional[int] = None,
    current_patient_name: Optional[str] = None,
):
    return SimpleNamespace(
        current_patient_id=current_patient_id,
        current_patient_name=current_patient_name,
    )


def _mock_db_ctx():
    mock_db = AsyncMock()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx, mock_db


# ============================================================================
# handle_query_records
# ============================================================================

class TestHandleQueryRecords:
    """Test handle_query_records — by name, by session, all records, empty."""

    @pytest.mark.asyncio
    async def test_query_by_name_found(self):
        """Explicit patient name → find patient → return their records."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name="张三")
        patient = _patient(pid=1, name="张三")
        records = [
            _record("头痛三天", datetime(2026, 3, 10)),
            _record("复查正常", datetime(2026, 3, 11)),
        ]

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=records), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        assert isinstance(result, HandlerResult)
        assert "张三" in result.reply
        assert "2 条" in result.reply

    @pytest.mark.asyncio
    async def test_query_by_name_not_found(self):
        """Patient name given but not in DB → not found message."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name="不存在")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=None), \
             patch(f"{_MOD}.set_patient_not_found") as mock_snf, \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        assert "未找到" in result.reply
        mock_snf.assert_called_once_with("doc1", "不存在")

    @pytest.mark.asyncio
    async def test_query_by_session_patient(self):
        """No name in intent, but session has current_patient → query that patient."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name=None)
        sess = _session(current_patient_id=5, current_patient_name="王五")
        records = [_record("检查结果")]

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_session", return_value=sess), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=records), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        assert "王五" in result.reply

    @pytest.mark.asyncio
    async def test_query_all_records(self):
        """No name, no session patient → return all records for doctor."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name=None)
        sess = _session()
        records = [
            _record("头痛", patient_name="张三"),
            _record("腰痛", patient_name="李四"),
        ]

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_session", return_value=sess), \
             patch(f"{_MOD}.get_all_records_for_doctor", new_callable=AsyncMock, return_value=records), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        assert "2 条" in result.reply
        assert len(result.records_list) == 2

    @pytest.mark.asyncio
    async def test_empty_all_records(self):
        """No records at all → empty message."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name=None)
        sess = _session()

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_session", return_value=sess), \
             patch(f"{_MOD}.get_all_records_for_doctor", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        assert "暂无" in result.reply

    @pytest.mark.asyncio
    async def test_empty_patient_records(self):
        """Patient found but has no records → empty message with patient name."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name="张三")
        patient = _patient(pid=1, name="张三")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.set_current_patient", return_value=None), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        assert "张三" in result.reply
        assert "暂无" in result.reply

    @pytest.mark.asyncio
    async def test_patient_switch_on_query_empty_records(self):
        """Querying a different patient with no records → switch notification set."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name="李四")
        patient = _patient(pid=2, name="李四")

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=[]), \
             patch(f"{_MOD}.set_current_patient", return_value="张三") as mock_scp, \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        mock_scp.assert_called_once_with("doc1", 2, "李四")
        assert result.switch_notification is not None
        assert "张三" in result.switch_notification

    @pytest.mark.asyncio
    async def test_set_current_patient_called_on_name_query(self):
        """Querying by name → set_current_patient is called to pin the patient."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name="李四")
        patient = _patient(pid=2, name="李四")
        records = [_record("检查", datetime(2026, 3, 10))]

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.find_patient_by_name", new_callable=AsyncMock, return_value=patient), \
             patch(f"{_MOD}.get_records_for_patient", new_callable=AsyncMock, return_value=records), \
             patch(f"{_MOD}.set_current_patient", return_value="张三") as mock_scp, \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        mock_scp.assert_called_once_with("doc1", 2, "李四")

    @pytest.mark.asyncio
    async def test_record_formatting_content_truncation(self):
        """Long content is truncated at 60 chars in the formatted output."""
        from services.domain.intent_handlers._query_records import handle_query_records
        ir = _intent(name=None)
        sess = _session()
        long_content = "A" * 100
        records = [_record(long_content, patient_name="张三")]

        mock_ctx, mock_db = _mock_db_ctx()
        with patch(f"{_MOD}.AsyncSessionLocal", return_value=mock_ctx), \
             patch(f"{_MOD}.get_session", return_value=sess), \
             patch(f"{_MOD}.get_all_records_for_doctor", new_callable=AsyncMock, return_value=records), \
             patch(f"{_MOD}.audit", new_callable=AsyncMock), \
             patch(f"{_MOD}.get_current_trace_id", return_value="t1"), \
             patch(f"{_MOD}.trace_block", _noop_trace):
            result = await handle_query_records("doc1", ir)

        # Content should be truncated to first 60 chars
        assert "A" * 60 in result.reply
        assert "A" * 100 not in result.reply
