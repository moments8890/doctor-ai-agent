"""Tests for admin cross-doctor patients endpoint.

Verifies ``GET /api/admin/patients``:

* Super token returns 200 with documented shape.
* Viewer token returns 200 (read-only access).
* Missing token returns 401.
* `q` filter narrows by patient name.

Drives the FastAPI app in-process with httpx ASGITransport (mirrors
`test_admin_ops.py`).
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
from db.models import Doctor, Patient, PatientMessage
from channels.web.doctor_dashboard.admin_patients import router as _patients_router


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
async def _seeded_session(_engine):
    """Insert a couple of doctors + patients so the endpoint has data to return."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    async with Session() as session:
        d1 = Doctor(doctor_id="doc__alpha", name="王明远")
        d2 = Doctor(doctor_id="doc__beta", name="李小姐")
        session.add_all([d1, d2])
        await session.flush()

        p1 = Patient(doctor_id="doc__alpha", name="陈玉琴", gender="female", year_of_birth=1962)
        p2 = Patient(doctor_id="doc__alpha", name="张三", gender="male", year_of_birth=1975)
        p3 = Patient(doctor_id="doc__beta", name="陈伟",  gender="male", year_of_birth=1980)
        session.add_all([p1, p2, p3])
        await session.flush()

        # one message so last_message_at / message_count_30d aren't all null
        session.add(
            PatientMessage(
                doctor_id="doc__alpha",
                patient_id=p1.id,
                direction="inbound",
                source="patient",
                content="hello",
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    return Session


@pytest_asyncio.fixture
async def async_client(_engine, _seeded_session, monkeypatch):
    monkeypatch.setenv("UI_ADMIN_TOKEN", SUPER_TOKEN)
    monkeypatch.setenv("UI_ADMIN_VIEWER_TOKEN", VIEWER_TOKEN)

    Session = _seeded_session

    async def _override_get_db():
        async with Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_patients_router)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_with_super_token_returns_items(async_client):
    """Super token returns 200 with the documented payload shape."""
    resp = await async_client.get(
        "/api/admin/patients",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"items", "total", "limit", "offset"}.issubset(body.keys()), body
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert isinstance(body["items"], list)
    assert body["total"] == 3, body
    assert len(body["items"]) == 3
    sample = body["items"][0]
    expected_item_keys = {
        "id",
        "name",
        "gender",
        "year_of_birth",
        "doctor_id",
        "doctor_name",
        "last_message_at",
        "message_count_30d",
        "record_count",
        "risk",
    }
    assert expected_item_keys.issubset(sample.keys()), sample


@pytest.mark.asyncio
async def test_get_with_viewer_token_succeeds(async_client):
    """Viewer-role token can read this endpoint (it's read-only)."""
    resp = await async_client.get(
        "/api/admin/patients",
        headers={"X-Admin-Token": VIEWER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert body["total"] == 3


@pytest.mark.asyncio
async def test_get_without_token_returns_401(async_client):
    """Missing X-Admin-Token → 401 from the role check."""
    resp = await async_client.get("/api/admin/patients")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_q_filter_narrows_by_name(async_client):
    """`q=陈` matches both 陈玉琴 and 陈伟 but not 张三."""
    resp = await async_client.get(
        "/api/admin/patients",
        params={"q": "陈"},
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = sorted(item["name"] for item in body["items"])
    assert names == ["陈伟", "陈玉琴"], body
    assert body["total"] == 2
