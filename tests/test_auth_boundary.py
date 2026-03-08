"""Security boundary tests: auth enforcement, admin token protection,
cross-doctor isolation, and rate-limit 429 behaviour."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Test 1 & 2: Unauthorized access — fallback flag OFF → 401
# ---------------------------------------------------------------------------

def test_tasks_endpoint_no_auth_fallback_off_raises_401():
    """GET /api/tasks without auth and fallback disabled must raise 401."""
    import routers.tasks as tasks_mod

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            # resolve_doctor_id_from_auth_or_fallback is called synchronously
            # inside the endpoint helper; we can call it directly here.
            from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
            resolve_doctor_id_from_auth_or_fallback(
                "some_doctor",
                None,
                fallback_env_flag="TASKS_ALLOW_BODY_DOCTOR_ID",
                default_doctor_id="test_doctor",
            )

    assert exc_info.value.status_code == 401


def test_neuro_endpoint_no_auth_fallback_off_raises_401():
    """POST /api/neuro/from-text without auth and fallback disabled → 401."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
            resolve_doctor_id_from_auth_or_fallback(
                "body_doctor",
                None,
                fallback_env_flag="NEURO_ALLOW_BODY_DOCTOR_ID",
                default_doctor_id="test_doctor",
            )

    assert exc_info.value.status_code == 401


def test_ui_endpoint_no_auth_fallback_off_raises_401():
    """UI manage-patients without auth and UI_ALLOW_QUERY_DOCTOR_ID=off → 401."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            from services.auth.request_auth import resolve_doctor_id_from_auth_or_fallback
            resolve_doctor_id_from_auth_or_fallback(
                "web_doctor",
                None,
                fallback_env_flag="UI_ALLOW_QUERY_DOCTOR_ID",
                default_doctor_id="web_doctor",
            )

    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Test 3 & 4: Admin token protection
# ---------------------------------------------------------------------------

def test_admin_endpoint_missing_token_raises_503_or_403():
    """Calling an admin endpoint without UI_ADMIN_TOKEN configured → 503."""
    from services.auth.request_auth import require_admin_token

    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            require_admin_token(None, env_name="UI_ADMIN_TOKEN")

    assert exc_info.value.status_code == 503


def test_admin_endpoint_wrong_token_raises_403():
    """Providing a wrong admin token when UI_ADMIN_TOKEN is set → 403."""
    from services.auth.request_auth import require_admin_token

    with patch.dict("os.environ", {"UI_ADMIN_TOKEN": "correct-secret"}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            require_admin_token("wrong-value", env_name="UI_ADMIN_TOKEN")

    assert exc_info.value.status_code == 403


def test_admin_endpoint_correct_token_passes():
    """Correct admin token must not raise."""
    from services.auth.request_auth import require_admin_token

    with patch.dict("os.environ", {"UI_ADMIN_TOKEN": "correct-secret"}, clear=True):
        # Should not raise
        require_admin_token("correct-secret", env_name="UI_ADMIN_TOKEN")


# ---------------------------------------------------------------------------
# Test 5 & 6: Cross-doctor isolation at CRUD layer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cross_doctor_patient_isolation(db_session):
    """Doctor A's patients are not visible to Doctor B."""
    from db.crud import create_patient, get_all_patients

    # Create a patient for doctor_a
    await create_patient(db_session, "doctor_a", "Patient Alpha", "F", 40)
    await db_session.commit()

    # Doctor B should see zero patients
    patients_b = await get_all_patients(db_session, "doctor_b")
    assert patients_b == []

    # Doctor A should see exactly one patient
    patients_a = await get_all_patients(db_session, "doctor_a")
    assert len(patients_a) == 1
    assert patients_a[0].name == "Patient Alpha"


@pytest.mark.asyncio
async def test_cross_doctor_records_isolation(db_session):
    """Doctor A's records are not returned when queried as Doctor B."""
    from db.crud import (
        create_patient,
        get_records_for_patient,
        save_record,
    )
    from models.medical_record import MedicalRecord

    # Create patient + record for doctor_a
    patient = await create_patient(db_session, "doctor_a", "Shared Name", "M", 50)
    await db_session.commit()

    record = MedicalRecord(chief_complaint="headache")
    await save_record(db_session, "doctor_a", record, patient.id)
    await db_session.commit()

    # Doctor B queries the same patient_id — should get nothing because
    # get_records_for_patient filters by doctor_id.
    records_b = await get_records_for_patient(db_session, "doctor_b", patient.id)
    assert records_b == []

    # Doctor A can read their own record
    records_a = await get_records_for_patient(db_session, "doctor_a", patient.id)
    assert len(records_a) == 1


# ---------------------------------------------------------------------------
# Test 7 & 8: Rate limiting
# ---------------------------------------------------------------------------

def test_rate_limit_429_raised_after_limit_exceeded():
    """enforce_doctor_rate_limit raises 429 once the per-window limit is hit."""
    from services.auth.rate_limit import enforce_doctor_rate_limit, clear_rate_limits_for_tests

    clear_rate_limits_for_tests()
    try:
        for _ in range(3):
            enforce_doctor_rate_limit("doc_rl", scope="test.scope", max_requests=3)

        with pytest.raises(HTTPException) as exc_info:
            enforce_doctor_rate_limit("doc_rl", scope="test.scope", max_requests=3)

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "rate_limit_exceeded"
    finally:
        clear_rate_limits_for_tests()


def test_rate_limit_429_includes_retry_after_header():
    """The 429 response must carry a Retry-After header."""
    from services.auth.rate_limit import enforce_doctor_rate_limit, clear_rate_limits_for_tests

    clear_rate_limits_for_tests()
    try:
        for _ in range(1):
            enforce_doctor_rate_limit("doc_hdr", scope="test.header", max_requests=1)

        with pytest.raises(HTTPException) as exc_info:
            enforce_doctor_rate_limit("doc_hdr", scope="test.header", max_requests=1)

        headers = exc_info.value.headers or {}
        assert "Retry-After" in headers
        assert int(headers["Retry-After"]) > 0
    finally:
        clear_rate_limits_for_tests()


def test_rate_limit_scopes_are_independent():
    """Different scopes for the same doctor do not share counters."""
    from services.auth.rate_limit import enforce_doctor_rate_limit, clear_rate_limits_for_tests

    clear_rate_limits_for_tests()
    try:
        # Fill scope A to the limit
        for _ in range(2):
            enforce_doctor_rate_limit("doc_scope", scope="scope.a", max_requests=2)

        # scope B should still be allowed (independent counter)
        enforce_doctor_rate_limit("doc_scope", scope="scope.b", max_requests=2)

        # scope A should now be blocked
        with pytest.raises(HTTPException) as exc_info:
            enforce_doctor_rate_limit("doc_scope", scope="scope.a", max_requests=2)

        assert exc_info.value.status_code == 429
    finally:
        clear_rate_limits_for_tests()
