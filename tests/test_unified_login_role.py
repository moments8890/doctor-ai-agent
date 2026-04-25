"""Regression: unified login must honor the role tab.

Doctor and patient accounts are independent — same nickname can exist as both.
Without a role hint, login() returns a role picker. With role="doctor", only
the doctor record is returned, even when a patient with the same nickname /
passcode exists. Vice versa for role="patient".
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("ENVIRONMENT", "test")  # _secret() requires non-prod env

from db.engine import Base
import db.models  # noqa: F401  — register all models
from db.models import Doctor, Patient
from infra.auth.unified import login
from utils.hashing import hash_passcode


NICK = "alice"
PASSCODE = "1990"


@pytest_asyncio.fixture
async def session_factory(monkeypatch):
    """Yield a session factory backed by in-memory SQLite, wired into login()."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # login() does `from db.engine import AsyncSessionLocal` inside its body,
    # so patching the attribute on the module is sufficient.
    import db.engine as engine_mod
    monkeypatch.setattr(engine_mod, "AsyncSessionLocal", factory)

    async with factory() as setup:
        setup.add(Doctor(
            doctor_id="doc_alice", name=NICK,
            nickname=NICK, passcode_hash=hash_passcode(PASSCODE),
        ))
        setup.add(Patient(
            doctor_id="doc_other", name=NICK,
            nickname=NICK, passcode_hash=hash_passcode(PASSCODE),
        ))
        await setup.commit()

    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_login_without_role_returns_picker(session_factory):
    """Sanity: unchanged behavior — both records match → role picker."""
    out = await login(NICK, PASSCODE)
    assert out.get("needs_role_selection") is True
    roles = {r["role"] for r in out["roles"]}
    assert roles == {"doctor", "patient"}


@pytest.mark.asyncio
async def test_login_doctor_role_skips_patient_table(session_factory):
    out = await login(NICK, PASSCODE, role="doctor")
    assert out.get("needs_role_selection") is None
    assert out["role"] == "doctor"
    assert out["doctor_id"] == "doc_alice"
    assert out["patient_id"] is None
    assert out["token"]


@pytest.mark.asyncio
async def test_login_patient_role_skips_doctor_table(session_factory):
    out = await login(NICK, PASSCODE, role="patient")
    assert out.get("needs_role_selection") is None
    assert out["role"] == "patient"
    assert out["doctor_id"] == "doc_other"
    assert out["patient_id"] is not None
    assert out["token"]


@pytest.mark.asyncio
async def test_login_role_only_matches_its_table(session_factory):
    """A doctor-only nickname can't be logged into via role='patient'."""
    from fastapi import HTTPException

    factory = session_factory
    async with factory() as s:
        s.add(Doctor(
            doctor_id="doc_solo", name="bob",
            nickname="bob", passcode_hash=hash_passcode("1985"),
        ))
        await s.commit()

    out = await login("bob", "1985", role="doctor")
    assert out["doctor_id"] == "doc_solo"

    with pytest.raises(HTTPException) as exc:
        await login("bob", "1985", role="patient")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_passcode_rejected(session_factory):
    """Wrong passcode → 401, never matches a hash."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await login(NICK, "0000", role="doctor")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_lockout_after_threshold_failures(session_factory, monkeypatch):
    """3 wrong passcodes → account locks; correct passcode then refused.

    All login failures (wrong passcode, locked account, no such user)
    return a uniform HTTP 401 to avoid leaking account state via status
    codes. A locked account is observable via the user's own /me path
    or the lockout-cleared timestamp, not via login response.
    """
    from fastapi import HTTPException
    from sqlalchemy import select
    import infra.auth.unified as auth_mod

    monkeypatch.setattr(auth_mod, "_LOGIN_FAIL_THRESHOLD", 3)
    monkeypatch.setattr(auth_mod, "_LOGIN_LOCK_SECONDS", 7 * 86400)

    for _ in range(3):
        with pytest.raises(HTTPException) as exc:
            await login(NICK, "0000", role="doctor")
        assert exc.value.status_code == 401

    # Correct passcode is now also refused (locked) — same 401, not 423.
    with pytest.raises(HTTPException) as exc:
        await login(NICK, PASSCODE, role="doctor")
    assert exc.value.status_code == 401

    # Verify the lock actually landed in the DB.
    factory = session_factory
    async with factory() as s:
        d = (await s.execute(select(Doctor).where(Doctor.nickname == NICK))).scalar_one()
        assert d.passcode_locked_until is not None
        assert d.passcode_failed_attempts >= 3


@pytest.mark.asyncio
async def test_success_resets_failure_counter(session_factory):
    """Failures below threshold + a success → counter cleared, no lock."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await login(NICK, "0000", role="doctor")

    out = await login(NICK, PASSCODE, role="doctor")
    assert out["role"] == "doctor"

    # Verify counter reset on row.
    factory = session_factory
    async with factory() as s:
        from sqlalchemy import select
        d = (await s.execute(select(Doctor).where(Doctor.nickname == NICK))).scalar_one()
        assert d.passcode_failed_attempts == 0
        assert d.passcode_locked_until is None


@pytest.mark.asyncio
async def test_forget_me_requires_correct_passcode(session_factory):
    """Wrong passcode → 401 and the user row is not deleted."""
    from fastapi import HTTPException
    from infra.auth.unified import forget_me
    from sqlalchemy import select

    factory = session_factory
    out = await login(NICK, PASSCODE, role="doctor")

    with pytest.raises(HTTPException) as exc:
        await forget_me(role="doctor", doctor_id=out["doctor_id"], passcode="WRONG")
    assert exc.value.status_code == 401

    async with factory() as s:
        d = (await s.execute(select(Doctor).where(Doctor.doctor_id == out["doctor_id"]))).scalar_one_or_none()
        assert d is not None  # still there


@pytest.mark.asyncio
async def test_forget_me_deletes_with_correct_passcode(session_factory):
    from infra.auth.unified import forget_me
    from sqlalchemy import select

    factory = session_factory
    out = await login(NICK, PASSCODE, role="doctor")

    result = await forget_me(role="doctor", doctor_id=out["doctor_id"], passcode=PASSCODE)
    assert result == {"ok": True, "deleted_role": "doctor"}

    async with factory() as s:
        d = (await s.execute(select(Doctor).where(Doctor.doctor_id == out["doctor_id"]))).scalar_one_or_none()
        assert d is None


@pytest.mark.asyncio
async def test_authenticate_rejects_token_for_deleted_user(session_factory):
    """P1.1 — token issued before forget_me must NOT pass authenticate().

    Regression for the codex review finding: _enforce_passcode_version
    used to default missing users to pcv=1, so an old token (pcv=1) for
    a deleted user would still authenticate.
    """
    from fastapi import HTTPException
    from infra.auth.unified import authenticate, forget_me

    out = await login(NICK, PASSCODE, role="doctor")
    auth_header = f"Bearer {out['token']}"

    payload = await authenticate(auth_header)  # warm token: ok
    assert payload["role"] == "doctor"

    await forget_me(role="doctor", doctor_id=out["doctor_id"], passcode=PASSCODE)

    with pytest.raises(HTTPException) as exc:
        await authenticate(auth_header)
    assert exc.value.status_code == 401
    assert "revoke" in (exc.value.detail or "").lower()


@pytest.mark.asyncio
async def test_patient_login_no_dos_via_shared_nickname(session_factory):
    """P1.2 — failed patient login via shared nickname must NOT lock out
    other patients across doctors.
    """
    from sqlalchemy import select
    factory = session_factory
    # Seed two patients sharing a nickname under different doctors.
    async with factory() as s:
        s.add(Patient(
            doctor_id="doc_alpha", name="shared",
            nickname="shared", passcode_hash=hash_passcode("aaaa"),
        ))
        s.add(Patient(
            doctor_id="doc_beta", name="shared",
            nickname="shared", passcode_hash=hash_passcode("bbbb"),
        ))
        await s.commit()

    # Hammer wrong passcode via the multi-candidate (no-selector) path.
    from fastapi import HTTPException
    for _ in range(10):
        with pytest.raises(HTTPException):
            await login("shared", "0000", role="patient")

    # Neither row's counter should have moved — the multi-candidate
    # path must refuse to penalize unrelated accounts.
    async with factory() as s:
        rows = (await s.execute(
            select(Patient).where(Patient.nickname == "shared")
        )).scalars().all()
        for p in rows:
            assert p.passcode_failed_attempts == 0
            assert p.passcode_locked_until is None


@pytest.mark.asyncio
async def test_login_with_role_patient_requires_selector(session_factory):
    """P1.2 — login_with_role(role=patient) without doctor_id/patient_id is 400."""
    from fastapi import HTTPException
    from infra.auth.unified import login_with_role
    with pytest.raises(HTTPException) as exc:
        await login_with_role("shared", "0000", role="patient")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_cross_role_shared_nickname_no_dos(session_factory):
    """N1 — login(role=None) with the same nickname in both roles must
    not lock either account on a wrong-passcode attempt.

    The session_factory fixture seeds nickname=alice as BOTH a doctor
    and a patient (different doctor_ids). A wrong-passcode attempt with
    role=None should leave both rows untouched.
    """
    from sqlalchemy import select
    from fastapi import HTTPException
    factory = session_factory

    for _ in range(10):
        with pytest.raises(HTTPException):
            await login(NICK, "0000")  # role=None — shared-nickname ambiguity

    async with factory() as s:
        d = (await s.execute(select(Doctor).where(Doctor.nickname == NICK))).scalar_one()
        p = (await s.execute(select(Patient).where(Patient.nickname == NICK))).scalar_one()
        assert d.passcode_failed_attempts == 0
        assert p.passcode_failed_attempts == 0


@pytest.mark.asyncio
async def test_uniform_401_no_user_vs_wrong_passcode(session_factory):
    """P2.6 — login response is the same status for missing-user and
    wrong-passcode paths (no enumeration via 401-vs-other status)."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc1:
        await login("does-not-exist-anywhere", "0000", role="doctor")
    with pytest.raises(HTTPException) as exc2:
        await login(NICK, "0000", role="doctor")
    assert exc1.value.status_code == 401
    assert exc2.value.status_code == 401


@pytest.mark.asyncio
async def test_revoke_user_tokens_kills_old_jwts(session_factory):
    """Bumping passcode_version invalidates any token issued at the old version."""
    from fastapi import HTTPException
    from infra.auth.unified import authenticate, revoke_user_tokens

    out = await login(NICK, PASSCODE, role="doctor")
    auth_header = f"Bearer {out['token']}"

    payload = await authenticate(auth_header)  # fresh token: ok
    assert payload["role"] == "doctor"

    await revoke_user_tokens(role="doctor", doctor_id=out["doctor_id"])

    with pytest.raises(HTTPException) as exc:
        await authenticate(auth_header)
    assert exc.value.status_code == 401
    assert "revoke" in (exc.value.detail or "").lower()
