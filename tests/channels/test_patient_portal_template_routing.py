"""Patient portal /start must honor an explicit template_id, fall back to
the doctor's ``preferred_template_id``, and finally default to
``medical_general_v1`` (Phase 4 r2 — bug A).

These are unit-level tests. External dependencies (patient auth, doctor
name lookup, active-session lookup, session creation, doctor DB row) are
mocked so the tests exercise only the handler + ``_resolve_start_template_id``
resolution logic.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from channels.web.patient_interview_routes import (
    InterviewStartRequest,
    start_interview,
)
from domain.patients.interview_session import InterviewSession


# ── helpers ──────────────────────────────────────────────────────────


def _make_patient(patient_id: int = 1, doctor_id: str = "dr_test") -> MagicMock:
    p = MagicMock()
    p.id = patient_id
    p.doctor_id = doctor_id
    p.name = f"Patient {patient_id}"
    return p


def _make_doctor(preferred_template_id):
    """Fake Doctor ORM row with a ``preferred_template_id`` attribute."""
    d = MagicMock()
    d.doctor_id = "dr_test"
    d.preferred_template_id = preferred_template_id
    return d


def _fake_async_session_local(doctor_row):
    """Return a factory that mimics ``AsyncSessionLocal()`` used as an async
    context manager. The inner ``db.execute(...).scalar_one_or_none()`` call
    yields ``doctor_row``.
    """

    @asynccontextmanager
    async def _factory():
        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=doctor_row)
        db.execute = AsyncMock(return_value=result)
        yield db

    # Calling the factory like ``AsyncSessionLocal()`` returns the
    # async context manager instance.
    return _factory


def _capture_create_session():
    """Return (capture dict, AsyncMock) where the mock captures kwargs."""
    captured = {}

    async def _inner(doctor_id, patient_id, *args, **kwargs):
        captured["doctor_id"] = doctor_id
        captured["patient_id"] = patient_id
        captured["template_id"] = kwargs.get("template_id")
        return InterviewSession(
            id="session-uuid-test",
            doctor_id=doctor_id,
            patient_id=patient_id,
            template_id=kwargs.get("template_id", "medical_general_v1"),
        )

    return captured, AsyncMock(side_effect=_inner)


def _patch_start_deps(doctor_row, create_session_mock):
    """Build the common patcher stack used by every test."""
    return [
        patch(
            "channels.web.patient_interview_routes._authenticate_patient",
            new_callable=AsyncMock,
            return_value=_make_patient(),
        ),
        patch(
            "channels.web.patient_interview_routes._get_doctor_name",
            new_callable=AsyncMock,
            return_value="测试医生",
        ),
        patch(
            "channels.web.patient_interview_routes.get_active_session",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "channels.web.patient_interview_routes.create_session",
            create_session_mock,
        ),
        patch(
            "db.engine.AsyncSessionLocal",
            _fake_async_session_local(doctor_row),
        ),
    ]


async def _run_start(
    *,
    doctor_row,
    explicit_template_id=None,
    body_template_id=None,
):
    captured, create_mock = _capture_create_session()
    patchers = _patch_start_deps(doctor_row, create_mock)
    for p in patchers:
        p.start()
    try:
        body = (
            InterviewStartRequest(template_id=body_template_id)
            if body_template_id is not None
            else None
        )
        resp = await start_interview(
            authorization="fake-token",
            template_id=explicit_template_id,
            body=body,
        )
        return resp, captured
    finally:
        for p in patchers:
            p.stop()


# ── tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_session_with_explicit_template_id():
    """Explicit template_id from the request wins over doctor preferences."""
    doctor = _make_doctor(preferred_template_id="form_satisfaction_v1")
    resp, captured = await _run_start(
        doctor_row=doctor,
        explicit_template_id="medical_general_v1",
    )

    assert captured["template_id"] == "medical_general_v1"
    assert resp["session_id"] == "session-uuid-test"
    assert resp["resumed"] is False


@pytest.mark.asyncio
async def test_start_session_falls_back_to_doctor_preferred_template():
    """With no request-level override, the doctor's preferred template wins."""
    doctor = _make_doctor(preferred_template_id="form_satisfaction_v1")
    resp, captured = await _run_start(doctor_row=doctor)

    assert captured["template_id"] == "form_satisfaction_v1"
    assert resp["session_id"] == "session-uuid-test"


@pytest.mark.asyncio
async def test_start_session_defaults_when_no_preference():
    """NULL preferred_template_id and no override → medical_general_v1."""
    doctor = _make_doctor(preferred_template_id=None)
    resp, captured = await _run_start(doctor_row=doctor)

    assert captured["template_id"] == "medical_general_v1"
    assert resp["session_id"] == "session-uuid-test"


@pytest.mark.asyncio
async def test_start_session_explicit_overrides_doctor_preferred():
    """Explicit template_id overrides a non-null doctor preference."""
    doctor = _make_doctor(preferred_template_id="medical_general_v1")
    _, captured = await _run_start(
        doctor_row=doctor,
        explicit_template_id="form_satisfaction_v1",
    )

    assert captured["template_id"] == "form_satisfaction_v1"


@pytest.mark.asyncio
async def test_start_session_rejects_unknown_template_id():
    """Unknown templates raise 422 with a clear message."""
    doctor = _make_doctor(preferred_template_id=None)
    with pytest.raises(HTTPException) as exc:
        await _run_start(
            doctor_row=doctor,
            explicit_template_id="does_not_exist_v9",
        )

    assert exc.value.status_code == 422
    assert "does_not_exist_v9" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_start_session_body_template_id_honored():
    """template_id supplied via JSON body (no query param) is resolved."""
    doctor = _make_doctor(preferred_template_id=None)
    _, captured = await _run_start(
        doctor_row=doctor,
        body_template_id="form_satisfaction_v1",
    )

    assert captured["template_id"] == "form_satisfaction_v1"
