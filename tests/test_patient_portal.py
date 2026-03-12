"""患者门户安全升级测试：access_code 认证、向后兼容、自动生成、消息持久化与通知。

Tests for the patient portal security upgrade:
  - Login with correct access code succeeds
  - Login with wrong access code returns 401
  - Legacy patient (no access_code) can still log in with deprecation warning
  - Access code is auto-generated on patient creation
  - set_patient_access_code generates a new code for existing patients
  - send_patient_message persists to DB and notifies doctor
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


# ---------------------------------------------------------------------------
# 9. send_patient_message — persists and notifies
# ---------------------------------------------------------------------------

def _mock_async_session_ctx(patient_obj):
    """Build an async context manager that mimics AsyncSessionLocal().

    The first __aenter__ call returns a session whose .execute() yields the
    patient lookup.  The second call returns a session used for save.
    """
    from unittest.mock import AsyncMock

    call_count = {"n": 0}

    class _FakeSession:
        async def execute(self, stmt):
            ns = SimpleNamespace()
            ns.scalar_one_or_none = lambda: patient_obj
            return ns

        async def commit(self):
            pass

    class _FakeSaveSession:
        add_called_with = None

        def add(self, obj):
            _FakeSaveSession.add_called_with = obj

        async def commit(self):
            pass

    class _CtxMgr:
        async def __aenter__(self):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _FakeSession()
            return _FakeSaveSession()

        async def __aexit__(self, *args):
            pass

    return _CtxMgr, _FakeSaveSession


@pytest.mark.asyncio
async def test_send_message_persists_and_notifies():
    """POST /api/patient/message persists the message and triggers doctor notification."""
    import asyncio
    from routers.patient_portal import send_patient_message, PatientMessageRequest

    patient = _make_patient(patient_id=10, name="赵六", doctor_id="doc_msg")

    ctx_cls, save_session_cls = _mock_async_session_ctx(patient)
    mock_save = AsyncMock()
    mock_notify = AsyncMock()

    with patch("routers.patient_portal._parse_patient_token_header", return_value=10), \
         patch("routers.patient_portal.AsyncSessionLocal", side_effect=lambda: ctx_cls()), \
         patch("routers.patient_portal.save_patient_message", mock_save), \
         patch("routers.patient_portal.send_doctor_notification", mock_notify), \
         patch("routers.patient_portal.audit", new_callable=AsyncMock):
        resp = await send_patient_message(
            PatientMessageRequest(text="我今天感觉好一些了"),
            x_patient_token="fake-token",
        )

        assert resp.reply == "您的消息已收到，医生将尽快回复您。"

        # Verify persistence was called with correct args
        mock_save.assert_awaited_once()
        call_kwargs = mock_save.call_args
        assert call_kwargs[1]["patient_id"] == 10
        assert call_kwargs[1]["doctor_id"] == "doc_msg"
        assert call_kwargs[1]["content"] == "我今天感觉好一些了"
        assert call_kwargs[1]["direction"] == "inbound"

        # Give fire-and-forget task a tick to execute within the patch context
        await asyncio.sleep(0)
        mock_notify.assert_awaited_once()
        notify_args = mock_notify.call_args[0]
        assert notify_args[0] == "doc_msg"
        assert "赵六" in notify_args[1]


@pytest.mark.asyncio
async def test_send_message_empty_text_returns_422():
    """POST /api/patient/message with empty text returns 422."""
    from routers.patient_portal import send_patient_message, PatientMessageRequest

    with patch("routers.patient_portal._parse_patient_token_header", return_value=10):
        with pytest.raises(HTTPException) as exc_info:
            await send_patient_message(
                PatientMessageRequest(text="   "),
                x_patient_token="fake-token",
            )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_send_message_patient_not_found_returns_404():
    """POST /api/patient/message for non-existent patient returns 404."""
    from routers.patient_portal import send_patient_message, PatientMessageRequest

    # AsyncSessionLocal returns a session whose execute yields None
    class _FakeSession:
        async def execute(self, stmt):
            ns = SimpleNamespace()
            ns.scalar_one_or_none = lambda: None
            return ns

    class _CtxMgr:
        async def __aenter__(self):
            return _FakeSession()
        async def __aexit__(self, *args):
            pass

    with patch("routers.patient_portal._parse_patient_token_header", return_value=999):
        with patch("routers.patient_portal.AsyncSessionLocal", return_value=_CtxMgr()):
            with pytest.raises(HTTPException) as exc_info:
                await send_patient_message(
                    PatientMessageRequest(text="你好医生"),
                    x_patient_token="fake-token",
                )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_notify_doctor_safe_swallows_exception():
    """_notify_doctor_safe catches exceptions and logs them without re-raising."""
    from routers.patient_portal import _notify_doctor_safe

    with patch(
        "routers.patient_portal.send_doctor_notification",
        new_callable=AsyncMock,
        side_effect=RuntimeError("network down"),
    ):
        # Should NOT raise
        await _notify_doctor_safe("doc_1", "test message")
