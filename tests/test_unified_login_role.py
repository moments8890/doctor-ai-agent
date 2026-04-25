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
