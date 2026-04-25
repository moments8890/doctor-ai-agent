"""Regression: every /api/admin/* read endpoint must require an admin token.

Production incident 2026-04-25: `https://api.doctoragentai.cn/api/admin/overview`
was leaking the dashboard (doctor list, interview counts, AI acceptance rates)
to the public internet. Root cause: every endpoint in
``channels.web.doctor_dashboard.admin_overview`` was registered without any
``Depends(require_admin_role)`` or header-based token check. The existing
``test_no_token`` in ``test_admin_viewer_role.py`` only exercised the cleanup
write endpoints, so the gap was invisible.

This test parametrizes over every admin GET endpoint we've added across the
repo and asserts that NO token → 401 (or 422 from FastAPI for missing required
header, which we accept). Add new admin endpoints here as part of the same PR
that adds them — keeps the auth contract honest going forward.
"""
from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import db.models  # noqa: F401 — register ORM models
from db.engine import Base, get_db
from channels.web.doctor_dashboard.admin_overview import router as _overview_router
from channels.web.doctor_dashboard.admin_cleanup import router as _cleanup_router
from channels.web.doctor_dashboard.admin_ops import router as _ops_router
from channels.web.doctor_dashboard.admin_patients import router as _patients_router
from channels.web.doctor_dashboard.admin_messages import router as _messages_router
from channels.web.doctor_dashboard.admin_suggestions import router as _suggestions_router


SUPER_TOKEN = "super-token-abc"
VIEWER_TOKEN = "viewer-token-xyz"


@pytest_asyncio.fixture
async def _engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client(_engine, monkeypatch):
    # Force production-mode auth checks so the test catches BOTH
    # ``Depends(require_admin_role)`` bypasses AND legacy
    # ``_require_ui_admin_access`` bypasses (the latter no-ops when
    # is_production() returns False — see infra.auth.request_auth).
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("UI_ADMIN_TOKEN", SUPER_TOKEN)
    monkeypatch.setenv("UI_ADMIN_VIEWER_TOKEN", VIEWER_TOKEN)

    Session = async_sessionmaker(_engine, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_overview_router)
    app.include_router(_cleanup_router)
    app.include_router(_ops_router)
    app.include_router(_patients_router)
    app.include_router(_messages_router)
    app.include_router(_suggestions_router)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# Every admin GET endpoint we expose. Parametrized so adding a new one
# without auth fails CI immediately.
ADMIN_GET_ENDPOINTS = [
    # admin_overview.py — the 8 that were leaking
    "/api/admin/overview",
    "/api/admin/doctors",
    "/api/admin/activity",
    "/api/admin/doctors/doc__placeholder",
    "/api/admin/doctors/doc__placeholder/patients",
    "/api/admin/doctors/doc__placeholder/timeline?patient_id=1",
    "/api/admin/doctors/doc__placeholder/related",
    "/api/admin/patients/1/related",
    # admin_cleanup.py
    "/api/admin/cleanup/preview",
    # admin_ops.py
    "/api/admin/ops/pilot-progress",
    "/api/admin/ops/partner-report",
    # admin_patients.py / admin_messages.py / admin_suggestions.py
    "/api/admin/patients",
    "/api/admin/messages/recent",
    "/api/admin/suggestions/recent",
]


# Accept both 401 (new role-based deps) and 403 (legacy require_admin_token).
# Both are proper rejections — the only failure we want to catch is 200.
_REJECT_STATUSES = {401, 403}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_GET_ENDPOINTS)
async def test_admin_endpoint_rejects_no_token(async_client, path):
    """No X-Admin-Token header → 401/403 (NOT 200)."""
    resp = await async_client.get(path)
    assert resp.status_code in _REJECT_STATUSES, (
        f"{path} returned {resp.status_code}: ADMIN DATA LEAK — "
        f"endpoint accepts requests without X-Admin-Token. "
        f"body={resp.text[:200]}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_GET_ENDPOINTS)
async def test_admin_endpoint_rejects_bad_token(async_client, path):
    """Wrong X-Admin-Token → 401/403."""
    resp = await async_client.get(path, headers={"X-Admin-Token": "bogus"})
    assert resp.status_code in _REJECT_STATUSES, (
        f"{path} returned {resp.status_code} for an invalid token: ADMIN DATA LEAK. "
        f"body={resp.text[:200]}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_GET_ENDPOINTS)
async def test_admin_endpoint_accepts_super_token(async_client, path):
    """Valid super token → NOT 401/403 (the endpoint may still 404/422 on
    placeholder ids, but it must not reject the token)."""
    resp = await async_client.get(path, headers={"X-Admin-Token": SUPER_TOKEN})
    assert resp.status_code not in (401, 403), (
        f"{path} rejected a valid super token: {resp.status_code} {resp.text[:200]}"
    )
