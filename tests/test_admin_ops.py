"""Task 3.3 — admin 运营 endpoints (pilot-progress, partner-report).

Verifies the two new read-only endpoints in
``channels.web.doctor_dashboard.admin_ops``:

* ``GET /api/admin/ops/pilot-progress`` returns the expected shape.
* ``GET /api/admin/ops/partner-report`` returns the expected shape.
* Missing tokens are rejected with 401.
* Viewer-role tokens (read-only) succeed — these endpoints are read-only.

Drives the FastAPI app in-process with httpx ASGITransport so the role
auth dependency is exercised end-to-end (mirrors test_admin_viewer_role.py).
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
from channels.web.doctor_dashboard.admin_ops import router as _ops_router


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
    monkeypatch.setenv("UI_ADMIN_TOKEN", SUPER_TOKEN)
    monkeypatch.setenv("UI_ADMIN_VIEWER_TOKEN", VIEWER_TOKEN)

    Session = async_sessionmaker(_engine, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_ops_router)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pilot_progress_with_super_token(async_client):
    """Pilot progress endpoint returns the documented shape under super token."""
    resp = await async_client.get(
        "/api/admin/ops/pilot-progress",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    expected_keys = {
        "start_date",
        "current_week",
        "total_weeks",
        "milestones",
        "doctors_active",
        "doctors_target",
    }
    assert expected_keys.issubset(body.keys()), body
    assert body["total_weeks"] == 24
    assert isinstance(body["milestones"], list)
    assert all(
        {"date", "label", "done"}.issubset(m.keys()) for m in body["milestones"]
    ), body["milestones"]
    assert body["doctors_target"] == 20


@pytest.mark.asyncio
async def test_pilot_progress_without_token_returns_401(async_client):
    """Calls without X-Admin-Token are rejected with 401."""
    resp = await async_client.get("/api/admin/ops/pilot-progress")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_partner_report_with_super_token(async_client):
    """Partner report endpoint returns the documented shape under super token."""
    resp = await async_client.get(
        "/api/admin/ops/partner-report",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    expected_keys = {
        "week",
        "start_date",
        "end_date",
        "adoption",
        "patient_active",
        "danger_signals_triggered",
        "top_doctors",
    }
    assert expected_keys.issubset(body.keys()), body
    assert {"rate", "total"}.issubset(body["adoption"].keys()), body["adoption"]
    assert isinstance(body["top_doctors"], list)


@pytest.mark.asyncio
async def test_partner_report_with_viewer_token_succeeds(async_client):
    """Viewer-role tokens get 200 — both ops endpoints are read-only."""
    resp = await async_client.get(
        "/api/admin/ops/partner-report",
        headers={"X-Admin-Token": VIEWER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "adoption" in body
