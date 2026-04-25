"""Tests for admin cross-doctor AI suggestions endpoint.

Verifies ``GET /api/admin/suggestions/recent``:

* Super token returns 200 with documented shape.
* Viewer token returns 200 (read-only access).
* Missing token returns 401.
* `q` filter narrows by patient name OR content substring.

Drives the FastAPI app in-process with httpx ASGITransport (mirrors
``test_admin_patients.py``).
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
from db.models import AISuggestion, Doctor, MedicalRecordDB, Patient
from channels.web.doctor_dashboard.admin_suggestions import router as _suggestions_router


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
    """Insert doctors + patients + records + suggestions covering each decision state."""
    Session = async_sessionmaker(_engine, expire_on_commit=False)
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

        r1 = MedicalRecordDB(doctor_id="doc__alpha", patient_id=p1.id, content="visit 1")
        r2 = MedicalRecordDB(doctor_id="doc__alpha", patient_id=p2.id, content="visit 2")
        r3 = MedicalRecordDB(doctor_id="doc__beta", patient_id=p3.id, content="visit 3")
        session.add_all([r1, r2, r3])
        await session.flush()

        # 4 suggestions across 3 patients with different decisions
        now = datetime.now(timezone.utc)
        session.add_all([
            AISuggestion(
                record_id=r1.id,
                doctor_id="doc__alpha",
                section="treatment",
                content="建议氨氯地平 5→10mg",
                decision="confirmed",
                cited_knowledge_ids="[1, 2]",
                created_at=now,
            ),
            AISuggestion(
                record_id=r2.id,
                doctor_id="doc__alpha",
                section="workup",
                content="建议查甲功",
                decision="edited",
                edited_text="查甲功 + TSH",
                cited_knowledge_ids="[7]",
                created_at=now,
            ),
            AISuggestion(
                record_id=r3.id,
                doctor_id="doc__beta",
                section="differential",
                content="鉴别诊断: 心衰",
                decision=None,  # pending
                created_at=now,
            ),
            AISuggestion(
                record_id=r3.id,
                doctor_id="doc__beta",
                section="treatment",
                content="减药方案",
                decision="rejected",
                created_at=now,
            ),
        ])
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
    app.include_router(_suggestions_router)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_with_super_token_returns_items(async_client):
    """Super token returns 200 with the documented payload shape."""
    resp = await async_client.get(
        "/api/admin/suggestions/recent",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {"items", "total", "limit", "offset"}.issubset(body.keys()), body
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert isinstance(body["items"], list)
    assert body["total"] == 4, body
    assert len(body["items"]) == 4
    sample = body["items"][0]
    expected_item_keys = {
        "id",
        "section",
        "decision",
        "patient_name",
        "doctor_id",
        "doctor_name",
        "content_preview",
        "cited_knowledge_count",
        "created_at",
    }
    assert expected_item_keys.issubset(sample.keys()), sample
    # Find the edited row — preview should reflect the edited_text override
    edited = next(it for it in body["items"] if it["decision"] == "edited")
    assert edited["content_preview"] == "查甲功 + TSH", edited
    assert edited["cited_knowledge_count"] == 1
    confirmed = next(it for it in body["items"] if it["decision"] == "confirmed")
    assert confirmed["cited_knowledge_count"] == 2


@pytest.mark.asyncio
async def test_get_with_viewer_token_succeeds(async_client):
    """Viewer-role token can read this endpoint (it's read-only)."""
    resp = await async_client.get(
        "/api/admin/suggestions/recent",
        headers={"X-Admin-Token": VIEWER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert body["total"] == 4


@pytest.mark.asyncio
async def test_get_without_token_returns_401(async_client):
    """Missing X-Admin-Token → 401 from the role check."""
    resp = await async_client.get("/api/admin/suggestions/recent")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_q_filter_matches_patient_or_content(async_client):
    """`q=陈` matches the two 陈* patients across both doctors."""
    resp = await async_client.get(
        "/api/admin/suggestions/recent",
        params={"q": "陈"},
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 陈玉琴 (1 suggestion) + 陈伟 (2 suggestions) = 3
    names = sorted({item["patient_name"] for item in body["items"]})
    assert names == ["陈伟", "陈玉琴"], body
    assert body["total"] == 3, body
