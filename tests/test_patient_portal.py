"""患者门户安全升级测试：access_code 认证、向后兼容、自动生成。

Tests for the patient portal security upgrade:
  - Login with correct access code succeeds
  - Login with wrong access code returns 401
  - Legacy patient (no access_code) can still log in with deprecation warning
  - Access code is auto-generated on patient creation
  - set_patient_access_code generates a new code for existing patients
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services.auth.access_code_hash import (
    generate_access_code,
    hash_access_code,
    verify_access_code,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_patient(
    patient_id: int = 1,
    name: str = "张三",
    doctor_id: str = "doc_1",
    access_code_hash: Optional[str] = None,
) -> SimpleNamespace:
    """Create a lightweight Patient-like object for unit tests."""
    return SimpleNamespace(
        id=patient_id,
        name=name,
        doctor_id=doctor_id,
        access_code=access_code_hash,
    )


# ---------------------------------------------------------------------------
# 1. generate_access_code — format & randomness
# ---------------------------------------------------------------------------

def test_generate_access_code_returns_6_digits():
    code = generate_access_code()
    assert len(code) == 6
    assert code.isdigit()


def test_generate_access_code_is_random():
    codes = {generate_access_code() for _ in range(50)}
    # With 10^6 possibilities, 50 codes should be mostly unique.
    assert len(codes) > 1


# ---------------------------------------------------------------------------
# 2. hash_access_code / verify_access_code round-trip
# ---------------------------------------------------------------------------

def test_hash_and_verify_round_trip():
    code = "482901"
    hashed = hash_access_code(code)
    assert verify_access_code(code, hashed)


def test_verify_access_code_wrong_code():
    hashed = hash_access_code("123456")
    assert not verify_access_code("654321", hashed)


def test_verify_access_code_corrupt_hash():
    assert not verify_access_code("123456", "garbage")


def test_verify_access_code_empty_stored():
    assert not verify_access_code("123456", "")


# ---------------------------------------------------------------------------
# 3. _verify_patient_access_code — portal-level verification
# ---------------------------------------------------------------------------

def test_portal_verify_correct_code():
    """Correct access code does not raise."""
    from routers.patient_portal import _verify_patient_access_code

    code = "998877"
    patient = _make_patient(access_code_hash=hash_access_code(code))
    # Should NOT raise
    _verify_patient_access_code(patient, code)


def test_portal_verify_wrong_code_raises_401():
    """Wrong access code raises HTTPException with 401."""
    from routers.patient_portal import _verify_patient_access_code

    patient = _make_patient(access_code_hash=hash_access_code("111111"))
    with pytest.raises(HTTPException) as exc_info:
        _verify_patient_access_code(patient, "222222")
    assert exc_info.value.status_code == 401


def test_portal_verify_empty_code_raises_401():
    """Empty supplied code raises 401 when patient has an access_code."""
    from routers.patient_portal import _verify_patient_access_code

    patient = _make_patient(access_code_hash=hash_access_code("111111"))
    with pytest.raises(HTTPException) as exc_info:
        _verify_patient_access_code(patient, "")
    assert exc_info.value.status_code == 401


def test_portal_verify_legacy_patient_no_code_allows_login(caplog):
    """Legacy patient (access_code=None) is allowed with a deprecation warning."""
    from routers.patient_portal import _verify_patient_access_code

    patient = _make_patient(access_code_hash=None)
    with caplog.at_level(logging.WARNING, logger="routers.patient_portal"):
        # Should NOT raise
        _verify_patient_access_code(patient, "")

    assert "DEPRECATION" in caplog.text
    assert "name-only login" in caplog.text


def test_portal_verify_legacy_patient_ignores_supplied_code(caplog):
    """Legacy patient with no stored code: supplied code is ignored (still allowed)."""
    from routers.patient_portal import _verify_patient_access_code

    patient = _make_patient(access_code_hash=None)
    with caplog.at_level(logging.WARNING, logger="routers.patient_portal"):
        _verify_patient_access_code(patient, "999999")

    assert "DEPRECATION" in caplog.text


# ---------------------------------------------------------------------------
# 4. create_patient auto-generates access code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_patient_generates_access_code(db_session):
    """create_patient stores a hashed access_code and exposes plaintext transiently."""
    from db.crud import create_patient

    patient = await create_patient(db_session, "doc_portal", "李四", "男", 45)
    await db_session.commit()

    # The hashed code is stored in the DB column
    assert patient.access_code is not None
    assert patient.access_code.startswith("pbkdf2sha256$")

    # The plaintext is available on the transient attribute
    plaintext = getattr(patient, "_plaintext_access_code", None)
    assert plaintext is not None
    assert len(plaintext) == 6
    assert plaintext.isdigit()

    # The plaintext verifies against the stored hash
    assert verify_access_code(plaintext, patient.access_code)


# ---------------------------------------------------------------------------
# 5. set_patient_access_code — reset code for existing patient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_patient_access_code(db_session):
    """set_patient_access_code generates a new code and updates the DB row."""
    from db.crud import create_patient, set_patient_access_code

    patient = await create_patient(db_session, "doc_portal2", "王五", "女", 30)
    await db_session.commit()
    old_hash = patient.access_code

    new_plaintext = await set_patient_access_code(db_session, "doc_portal2", patient.id)
    assert len(new_plaintext) == 6
    assert new_plaintext.isdigit()

    # Refresh to see the updated hash
    await db_session.refresh(patient)
    assert patient.access_code != old_hash
    assert verify_access_code(new_plaintext, patient.access_code)


@pytest.mark.asyncio
async def test_set_patient_access_code_not_found_raises(db_session):
    """set_patient_access_code raises PatientNotFoundError for non-existent patient."""
    from db.crud import set_patient_access_code
    from utils.errors import PatientNotFoundError

    with pytest.raises(PatientNotFoundError):
        await set_patient_access_code(db_session, "doc_nonexist", 99999)


# ---------------------------------------------------------------------------
# 6. Full session endpoint — correct code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_endpoint_correct_code():
    """POST /api/patient/session with correct access_code returns a token."""
    from routers.patient_portal import create_patient_session, PatientSessionRequest
    from services.auth.rate_limit import clear_rate_limits_for_tests

    clear_rate_limits_for_tests()
    code = "123456"
    patient = _make_patient(access_code_hash=hash_access_code(code))

    with patch("routers.patient_portal._lookup_patient_by_name", new_callable=AsyncMock, return_value=patient):
        with patch("routers.patient_portal.audit", new_callable=AsyncMock):
            resp = await create_patient_session(
                PatientSessionRequest(doctor_id="doc_1", patient_name="张三", access_code=code)
            )

    assert resp.patient_id == 1
    assert resp.patient_name == "张三"
    assert resp.token  # non-empty JWT
    clear_rate_limits_for_tests()


# ---------------------------------------------------------------------------
# 7. Full session endpoint — wrong code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_endpoint_wrong_code():
    """POST /api/patient/session with wrong access_code returns 401."""
    from routers.patient_portal import create_patient_session, PatientSessionRequest
    from services.auth.rate_limit import clear_rate_limits_for_tests

    clear_rate_limits_for_tests()
    patient = _make_patient(access_code_hash=hash_access_code("123456"))

    with patch("routers.patient_portal._lookup_patient_by_name", new_callable=AsyncMock, return_value=patient):
        with pytest.raises(HTTPException) as exc_info:
            await create_patient_session(
                PatientSessionRequest(doctor_id="doc_1", patient_name="张三", access_code="000000")
            )

    assert exc_info.value.status_code == 401
    clear_rate_limits_for_tests()


# ---------------------------------------------------------------------------
# 8. Full session endpoint — legacy patient (no code)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_endpoint_legacy_patient_no_code(caplog):
    """POST /api/patient/session for legacy patient (no access_code) succeeds with warning."""
    from routers.patient_portal import create_patient_session, PatientSessionRequest
    from services.auth.rate_limit import clear_rate_limits_for_tests

    clear_rate_limits_for_tests()
    patient = _make_patient(access_code_hash=None)

    with patch("routers.patient_portal._lookup_patient_by_name", new_callable=AsyncMock, return_value=patient):
        with patch("routers.patient_portal.audit", new_callable=AsyncMock):
            with caplog.at_level(logging.WARNING, logger="routers.patient_portal"):
                resp = await create_patient_session(
                    PatientSessionRequest(doctor_id="doc_1", patient_name="张三")
                )

    assert resp.patient_id == 1
    assert resp.token
    assert "DEPRECATION" in caplog.text
    clear_rate_limits_for_tests()
