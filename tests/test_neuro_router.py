from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import routers.neuro as neuro


class _SessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_neuro_from_text_empty_input_raises_422():
    with pytest.raises(HTTPException) as exc:
        await neuro.neuro_from_text(neuro.NeuroFromTextInput(text="   "))
    assert exc.value.status_code == 422
    assert "cannot be empty" in exc.value.detail


async def test_neuro_from_text_value_error_maps_to_422(monkeypatch):
    monkeypatch.setattr(neuro, "extract_neuro_case", AsyncMock(side_effect=ValueError("bad schema")))
    with pytest.raises(HTTPException) as exc:
        await neuro.neuro_from_text(neuro.NeuroFromTextInput(text="raw"))
    assert exc.value.status_code == 422
    assert exc.value.detail == "Invalid neuro case content"


async def test_neuro_from_text_unexpected_error_maps_to_500(monkeypatch):
    monkeypatch.setattr(neuro, "extract_neuro_case", AsyncMock(side_effect=RuntimeError("boom")))
    with pytest.raises(HTTPException) as exc:
        await neuro.neuro_from_text(neuro.NeuroFromTextInput(text="raw"))
    assert exc.value.status_code == 500
    assert exc.value.detail == "Internal server error"


async def test_neuro_from_text_success_persists_and_returns_payload(monkeypatch):
    case_obj = MagicMock()
    case_obj.model_dump.return_value = {"patient_profile": {"name": "张三"}}
    log_obj = MagicMock()
    log_obj.model_dump.return_value = {"missing_fields": []}
    monkeypatch.setattr(neuro, "extract_neuro_case", AsyncMock(return_value=(case_obj, log_obj)))
    monkeypatch.setattr(neuro, "AsyncSessionLocal", lambda: _SessionCtx())
    monkeypatch.setattr(
        neuro,
        "save_neuro_case",
        AsyncMock(return_value=SimpleNamespace(id=88)),
    )

    data = await neuro.neuro_from_text(
        neuro.NeuroFromTextInput(text="患者张三，突发言语不清", doctor_id="doc_neuro"),
    )

    assert data["case"]["patient_profile"]["name"] == "张三"
    assert data["log"]["missing_fields"] == []
    assert data["db_id"] == 88


async def test_list_neuro_cases_shapes_response(monkeypatch):
    monkeypatch.setattr(neuro, "AsyncSessionLocal", lambda: _SessionCtx())
    monkeypatch.setattr(
        neuro,
        "get_neuro_cases_for_doctor",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    patient_name="李四",
                    chief_complaint="右侧肢体无力",
                    primary_diagnosis="急性脑梗死",
                    nihss=6,
                    created_at=datetime(2026, 3, 2, 9, 30, 0),
                ),
                SimpleNamespace(
                    id=2,
                    patient_name=None,
                    chief_complaint=None,
                    primary_diagnosis=None,
                    nihss=None,
                    created_at=None,
                ),
            ]
        ),
    )

    rows = await neuro.list_neuro_cases(doctor_id="doc_neuro", limit=2)

    assert len(rows) == 2
    assert rows[0].patient_name == "李四"
    assert rows[0].created_at == "2026-03-02T09:30:00"
    assert rows[1].created_at == ""
