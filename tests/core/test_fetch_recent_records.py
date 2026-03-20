"""_fetch_recent_records — cross-patient record retrieval."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_fetch_recent_records_returns_serialized_list():
    mock_record = MagicMock()
    mock_record.id = 1
    mock_record.content = "头痛三天"
    mock_record.tags = "[]"
    mock_record.record_type = "visit"
    mock_record.created_at = datetime(2026, 3, 20, 10, 0)

    with patch("db.engine.AsyncSessionLocal") as mock_session_cls, \
         patch("db.crud.records.get_all_records_for_doctor", new_callable=AsyncMock) as mock_query:
        mock_session = AsyncMock()
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_query.return_value = [mock_record]

        from agent.tools.doctor import _fetch_recent_records
        result = await _fetch_recent_records("dr_test", limit=5)

    assert len(result) == 1
    assert result[0]["id"] == 1
    assert result[0]["content"] == "头痛三天"
