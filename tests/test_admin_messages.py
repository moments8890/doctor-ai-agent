"""Tests for admin cross-doctor messages endpoint.

Verifies ``GET /api/admin/messages/recent``:

* Super token returns 200 with the documented payload shape.
* Viewer token returns 200 (read-only access).
* Missing token returns 401.
* `q` filter narrows by patient name.

Drives the FastAPI app in-process with httpx ASGITransport (mirrors
`test_admin_patients.py`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import db.models  # noqa: F401 — register all ORM models before create_all
from db.engine import Base, get_db
from db.models import Doctor, Patient, PatientMessage
from channels.web.doctor_dashboard.admin_messages import router as _messages_router


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
    """Seed two doctors, three patients, and a few messages spanning threads."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with Session() as session:
        d1 = Doctor(doctor_id="doc__alpha", name="王明远")
        d2 = Doctor(doctor_id="doc__beta", name="李小姐")
        session.add_all([d1, d2])
        await session.flush()

        p1 = Patient(doctor_id="doc__alpha", name="陈玉琴", gender="female", year_of_birth=1962)
        p2 = Patient(doctor_id="doc__alpha", name="张三", gender="male", year_of_birth=1975)
        p3 = Patient(doctor_id="doc__beta", name="陈伟", gender="male", year_of_birth=1980)
        session.add_all([p1, p2, p3])
        await session.flush()

        # Thread 1 (p1 ↔ doc__alpha): inbound → outbound → inbound (so 1 unread)
        session.add(PatientMessage(
            doctor_id="doc__alpha", patient_id=p1.id, direction="inbound",
            source="patient", content="医生，最近血压有点高",
            created_at=now - timedelta(hours=3),
        ))
        session.add(PatientMessage(
            doctor_id="doc__alpha", patient_id=p1.id, direction="outbound",
            source="doctor", content="建议早晚各测一次",
            created_at=now - timedelta(hours=2),
        ))
        session.add(PatientMessage(
            doctor_id="doc__alpha", patient_id=p1.id, direction="inbound",
            source="patient", content="好的，我记下了",
            created_at=now - timedelta(hours=1),
        ))

        # Thread 2 (p2 ↔ doc__alpha): single outbound — no unread
        session.add(PatientMessage(
            doctor_id="doc__alpha", patient_id=p2.id, direction="outbound",
            source="doctor", content="记得复查",
            created_at=now - timedelta(days=2),
        ))

        # Thread 3 (p3 ↔ doc__beta): single inbound — 1 unread
        session.add(PatientMessage(
            doctor_id="doc__beta", patient_id=p3.id, direction="inbound",
            source="patient", content="陈医生您好",
            created_at=now - timedelta(minutes=30),
        ))

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
    app.include_router(_messages_router)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_with_super_token_returns_items(async_client):
    """Super token returns 200 with the documented payload shape."""
    resp = await async_client.get(
        "/api/admin/messages/recent",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"items", "total", "limit", "offset"}.issubset(body.keys()), body
    assert body["limit"] == 50
    assert body["offset"] == 0
    # 3 distinct (patient, doctor) threads
    assert body["total"] == 3, body
    assert len(body["items"]) == 3
    sample = body["items"][0]
    expected_keys = {
        "patient_id", "patient_name",
        "doctor_id", "doctor_name",
        "last_message", "unread_count", "thread_message_count",
    }
    assert expected_keys.issubset(sample.keys()), sample
    msg = sample["last_message"]
    assert {"id", "direction", "content", "created_at"}.issubset(msg.keys()), msg
    # Items are ordered by latest message DESC — first should be p3 (30min ago).
    first = body["items"][0]
    assert first["patient_name"] == "陈伟"
    assert first["unread_count"] == 1


@pytest.mark.asyncio
async def test_get_with_viewer_token_succeeds(async_client):
    """Viewer-role token can read this endpoint (it's read-only)."""
    resp = await async_client.get(
        "/api/admin/messages/recent",
        headers={"X-Admin-Token": VIEWER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert body["total"] == 3


@pytest.mark.asyncio
async def test_get_without_token_returns_401(async_client):
    """Missing X-Admin-Token → 401 from the role check."""
    resp = await async_client.get("/api/admin/messages/recent")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_q_filter_narrows_by_patient_name(async_client):
    """`q=陈` matches both 陈玉琴 (doc__alpha) and 陈伟 (doc__beta)."""
    resp = await async_client.get(
        "/api/admin/messages/recent",
        params={"q": "陈"},
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = sorted(item["patient_name"] for item in body["items"])
    assert names == ["陈伟", "陈玉琴"], body
    assert body["total"] == 2
