"""Task 7: doctor /turn endpoint threads template_id through to create_session."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from channels.web.doctor_intake.turn import _first_turn


def _make_fake_session():
    fake = MagicMock()
    fake.id = "s1"
    fake.collected = {}
    fake.conversation = []
    fake.patient_id = None
    return fake


def _make_fake_response():
    resp = MagicMock()
    resp.collected = {}
    resp.patient_name = None
    resp.conversation = []
    resp.reply = ""
    resp.suggestions = []
    return resp


@pytest.mark.asyncio
async def test_first_turn_passes_template_id_to_create_session():
    fake_session = _make_fake_session()

    with patch("channels.web.doctor_intake.turn.create_session",
               new=AsyncMock(return_value=fake_session)) as mock_create, \
         patch("channels.web.doctor_intake.turn.save_session",
               new=AsyncMock()), \
         patch("channels.web.doctor_intake.turn._call_engine_turn",
               new=AsyncMock(return_value=_make_fake_response())), \
         patch("channels.web.doctor_intake.turn.resolve",
               new=AsyncMock(return_value={})):
        await _first_turn("doc", "hi", template_id="form_satisfaction_v1")

    kwargs = mock_create.call_args.kwargs
    assert kwargs["template_id"] == "form_satisfaction_v1"


@pytest.mark.asyncio
async def test_first_turn_defaults_template_id_when_none():
    fake_session = _make_fake_session()

    with patch("channels.web.doctor_intake.turn.create_session",
               new=AsyncMock(return_value=fake_session)) as mock_create, \
         patch("channels.web.doctor_intake.turn.save_session",
               new=AsyncMock()), \
         patch("channels.web.doctor_intake.turn._call_engine_turn",
               new=AsyncMock(return_value=_make_fake_response())), \
         patch("channels.web.doctor_intake.turn.resolve",
               new=AsyncMock(return_value={})):
        await _first_turn("doc", "hi")  # no template_id

    kwargs = mock_create.call_args.kwargs
    assert kwargs["template_id"] == "medical_general_v1"
