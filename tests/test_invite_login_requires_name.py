"""Test that POST /api/auth/invite/login rejects requests without a name.

Closes the orphan-doctor leak: prior to this change, the invite/login path
created Doctor rows with `name = invite.doctor_name`, which was often NULL.
Those rows surfaced as "(未命名医生)" in the admin dashboard and required a
toggle to see at all. Forcing a non-empty user-supplied name eliminates the
class entirely.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import db.models  # noqa: F401 — register all ORM models before create_all
from db.engine import Base, get_db
import db.engine as _engine_mod
from db.models import InviteCode
from channels.web.auth.invite import router as _invite_router


@pytest_asyncio.fixture
async def _engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(_engine, monkeypatch):
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    monkeypatch.setattr(_engine_mod, "AsyncSessionLocal", Session)
    # auth.invite caches AsyncSessionLocal at import time; patch its module
    # binding too so the route uses the in-memory session.
    import channels.web.auth.invite as _invite_mod
    monkeypatch.setattr(_invite_mod, "AsyncSessionLocal", Session)

    now = datetime.now(timezone.utc)
    async with Session() as session:
        session.add(
            InviteCode(
                code="MULTIBETA",
                doctor_id=None,
                doctor_name=None,
                max_uses=100,
                used_count=0,
                active=True,
                created_at=now,
            )
        )
        await session.commit()

    async def _override_get_db():
        async with Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_invite_router)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_missing_name_is_rejected(async_client):
    resp = await async_client.post(
        "/api/auth/invite/login", json={"code": "MULTIBETA"}
    )
    # 422 for Pydantic-level validation (field required).
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_blank_name_is_rejected(async_client):
    resp = await async_client.post(
        "/api/auth/invite/login", json={"code": "MULTIBETA", "name": "   "}
    )
    # Whitespace-only stripped → empty → 422 from explicit handler check.
    assert resp.status_code == 422
    assert "name" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_overlong_name_is_rejected(async_client):
    resp = await async_client.post(
        "/api/auth/invite/login",
        json={"code": "MULTIBETA", "name": "x" * 65},
    )
    assert resp.status_code == 422
