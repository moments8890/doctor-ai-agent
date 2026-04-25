"""Tests for the `include_unnamed` filter on GET /api/admin/doctors.

Default behavior (`include_unnamed=false`) hides rows with NULL name so the
admin list isn't cluttered by invite-link clicks that never reached the
nickname step. Operators can opt in to see them when investigating drop-off.
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
from db.models import Doctor
from channels.web.doctor_dashboard.admin_overview import router as _overview_router


SUPER_TOKEN = "super-token-abc"


@pytest_asyncio.fixture
async def _engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(_engine, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("UI_ADMIN_TOKEN", SUPER_TOKEN)

    Session = async_sessionmaker(_engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with Session() as session:
        session.add(Doctor(doctor_id="doc_named_a", name="王医生", created_at=now, updated_at=now))
        session.add(Doctor(doctor_id="doc_named_b", name="李医生", created_at=now, updated_at=now))
        session.add(Doctor(doctor_id="inv_orphan_x", name=None, created_at=now, updated_at=now))
        await session.commit()

    async def _override_get_db():
        async with Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_overview_router)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_default_hides_unnamed_doctors(async_client):
    resp = await async_client.get(
        "/api/admin/doctors", headers={"X-Admin-Token": SUPER_TOKEN}
    )
    assert resp.status_code == 200
    ids = {item["doctor_id"] for item in resp.json()["items"]}
    assert ids == {"doc_named_a", "doc_named_b"}


@pytest.mark.asyncio
async def test_include_unnamed_returns_orphans_too(async_client):
    resp = await async_client.get(
        "/api/admin/doctors?include_unnamed=true",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200
    ids = {item["doctor_id"] for item in resp.json()["items"]}
    assert ids == {"doc_named_a", "doc_named_b", "inv_orphan_x"}
