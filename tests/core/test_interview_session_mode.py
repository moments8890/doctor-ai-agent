"""Interview session mode field — doctor vs patient mode."""
import pytest
from unittest.mock import AsyncMock, patch
from db.models.interview_session import InterviewStatus


@pytest.mark.asyncio
async def test_create_session_with_doctor_mode():
    with patch("domain.patients.interview_session.AsyncSessionLocal") as mock_cls:
        mock_db = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        from domain.patients.interview_session import create_session
        session = await create_session("dr_test", 1, mode="doctor")
    assert session.mode == "doctor"
    assert session.doctor_id == "dr_test"
    assert session.patient_id == 1


@pytest.mark.asyncio
async def test_create_session_defaults_to_patient_mode():
    with patch("domain.patients.interview_session.AsyncSessionLocal") as mock_cls:
        mock_db = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        from domain.patients.interview_session import create_session
        session = await create_session("dr_test", 1)
    assert session.mode == "patient"


def test_interview_status_has_draft_created():
    assert hasattr(InterviewStatus, "draft_created")
    assert InterviewStatus.draft_created == "draft_created"
