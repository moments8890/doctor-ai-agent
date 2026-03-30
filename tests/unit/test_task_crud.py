"""Tests for task CRUD additions: completed_at tracking and notes update."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_update_status_sets_completed_at():
    """When status → completed, completed_at should be set."""
    from db.repositories.tasks import TaskRepository

    # Create a mock task object that behaves like a real SQLAlchemy model
    mock_task = MagicMock()
    mock_task.status = "pending"
    mock_task.completed_at = None

    # Mock the result object that session.execute returns
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_task)

    # Mock the session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    repo = TaskRepository(mock_session)
    result = await repo.update_status(task_id=1, doctor_id="doc1", status="completed")

    assert result is not None
    assert result.status == "completed"
    assert result.completed_at is not None
    assert mock_session.commit.called
    assert mock_session.refresh.called


@pytest.mark.asyncio
async def test_update_status_clears_completed_at_on_reopen():
    """When status reverts from completed, completed_at should be cleared."""
    from db.repositories.tasks import TaskRepository

    # Create a mock task with completed status
    mock_task = MagicMock()
    mock_task.status = "completed"
    mock_task.completed_at = datetime.now(timezone.utc)

    # Mock the result object
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_task)

    # Mock the session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    repo = TaskRepository(mock_session)
    result = await repo.update_status(task_id=1, doctor_id="doc1", status="pending")

    assert result is not None
    assert result.completed_at is None
    assert mock_session.commit.called
    assert mock_session.refresh.called


@pytest.mark.asyncio
async def test_update_notes():
    """update_notes should set the notes field."""
    from db.repositories.tasks import TaskRepository

    # Create a mock task
    mock_task = MagicMock()
    mock_task.notes = None

    # Mock the result object
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_task)

    # Mock the session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    repo = TaskRepository(mock_session)
    result = await repo.update_notes(task_id=1, doctor_id="doc1", notes="Patient called, reschedule needed")

    assert result is not None
    assert result.notes == "Patient called, reschedule needed"
    assert mock_session.commit.called
    assert mock_session.refresh.called
    # Verify get_by_id was called (which calls session.execute)
    assert mock_session.execute.called
