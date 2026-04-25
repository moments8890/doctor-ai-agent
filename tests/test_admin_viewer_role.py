"""Task 4.1 — viewer-role admin token.

Verifies the new role-aware admin auth in
``channels.web.doctor_dashboard.deps``:

* ``UI_ADMIN_TOKEN`` → role ``"super"`` (full access)
* ``UI_ADMIN_VIEWER_TOKEN`` → role ``"viewer"`` (reads only)
* viewers get 403 on destructive endpoints
* missing/invalid tokens get 401

The tests drive the FastAPI app in-process with httpx ASGITransport so the
full dependency chain (Header → role check → 401/403) is exercised.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import db.models  # noqa: F401 — register all ORM models before create_all
from db.engine import Base, get_db
from channels.web.doctor_dashboard.admin_cleanup import router as _cleanup_router
from channels.web.doctor_dashboard.admin_overview import router as _overview_router


SUPER_TOKEN = "super-token-abc"
VIEWER_TOKEN = "viewer-token-xyz"


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def _engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(_engine, monkeypatch):
    """In-process FastAPI client with both tokens configured."""
    monkeypatch.setenv("UI_ADMIN_TOKEN", SUPER_TOKEN)
    monkeypatch.setenv("UI_ADMIN_VIEWER_TOKEN", VIEWER_TOKEN)

    Session = async_sessionmaker(_engine, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_overview_router)
    app.include_router(_cleanup_router)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_token_can_read_overview(async_client):
    """Viewer tokens can hit read-only admin endpoints."""
    resp = await async_client.get(
        "/api/admin/overview",
        headers={"X-Admin-Token": VIEWER_TOKEN},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_viewer_token_cannot_cleanup(async_client):
    """Viewer tokens are rejected (403) on destructive cleanup endpoints."""
    resp = await async_client.post(
        "/api/admin/cleanup/execute?action=test_doctors",
        headers={"X-Admin-Token": VIEWER_TOKEN},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_super_token_can_cleanup(async_client):
    """Super tokens are allowed to run cleanup execute."""
    resp = await async_client.post(
        "/api/admin/cleanup/execute?action=test_doctors",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    # 200 OK with no test doctors to clean up — body is the deletion summary.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "deleted" in body and body["action"] == "test_doctors"


@pytest.mark.asyncio
async def test_no_token(async_client):
    """Missing X-Admin-Token → 401 from the role check."""
    resp = await async_client.post(
        "/api/admin/cleanup/execute?action=test_doctors",
    )
    assert resp.status_code == 401, resp.text
