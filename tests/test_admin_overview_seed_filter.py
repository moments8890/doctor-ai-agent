"""Tests for the `include_seeded` filter on /api/admin/overview.

Default behavior (`include_seeded=false`) must exclude rows tagged with
``seed_source`` so the partner-doctor pitch view doesn't read inflated
counts and 100% AI-acceptance ratios produced entirely by demo fixtures.
``include_seeded=true`` opt-in returns everything.

Surface tested:
* `secondary.new_patients` — Patient.created_at filter
* `hero.ai_acceptance.confirmed/edited/rejected` — AISuggestion.decision
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
from db.models import AISuggestion, Doctor, MedicalRecordDB, Patient
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
    yesterday = now - timedelta(days=1)

    async with Session() as session:
        session.add(
            Doctor(doctor_id="doc_real", name="Real Doc", created_at=now, updated_at=now)
        )
        # One real patient + one seeded patient, both within the 7d window.
        session.add(
            Patient(
                doctor_id="doc_real",
                name="Real Patient",
                gender="female",
                year_of_birth=1990,
                seed_source=None,
                created_at=yesterday,
            )
        )
        session.add(
            Patient(
                doctor_id="doc_real",
                name="Seeded Patient",
                gender="male",
                year_of_birth=1985,
                seed_source="onboarding_preseed",
                created_at=yesterday,
            )
        )

        # One real medical record so AISuggestion can FK to it cleanly.
        record = MedicalRecordDB(
            patient_id=1,
            doctor_id="doc_real",
            record_type="visit",
            seed_source=None,
            created_at=yesterday,
            updated_at=yesterday,
        )
        session.add(record)
        await session.flush()

        # Two confirmed AI suggestions: one real, one seeded.
        # Both decided in the 7d window so they enter the acceptance ratio.
        session.add(
            AISuggestion(
                record_id=record.id,
                doctor_id="doc_real",
                section="diagnosis",
                content="real",
                detail="real",
                decision="confirmed",
                decided_at=yesterday,
                seed_source=None,
            )
        )
        session.add(
            AISuggestion(
                record_id=record.id,
                doctor_id="doc_real",
                section="diagnosis",
                content="seeded",
                detail="seeded",
                decision="confirmed",
                decided_at=yesterday,
                seed_source="onboarding_preseed",
            )
        )
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
async def test_default_excludes_seeded_patients(async_client):
    resp = await async_client.get(
        "/api/admin/overview", headers={"X-Admin-Token": SUPER_TOKEN}
    )
    assert resp.status_code == 200
    body = resp.json()
    # Only the one real patient should be counted in the 7d window.
    assert body["secondary"]["new_patients"]["current"] == 1


@pytest.mark.asyncio
async def test_include_seeded_returns_all_patients(async_client):
    resp = await async_client.get(
        "/api/admin/overview?include_seeded=true",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["secondary"]["new_patients"]["current"] == 2


@pytest.mark.asyncio
async def test_default_excludes_seeded_ai_suggestions(async_client):
    resp = await async_client.get(
        "/api/admin/overview", headers={"X-Admin-Token": SUPER_TOKEN}
    )
    assert resp.status_code == 200
    accept = resp.json()["hero"]["ai_acceptance"]
    # Only the one real confirmed suggestion is counted.
    assert accept["confirmed"] == 1
    assert accept["edited"] == 0
    assert accept["rejected"] == 0


@pytest.mark.asyncio
async def test_include_seeded_counts_seeded_ai_suggestions(async_client):
    resp = await async_client.get(
        "/api/admin/overview?include_seeded=true",
        headers={"X-Admin-Token": SUPER_TOKEN},
    )
    assert resp.status_code == 200
    accept = resp.json()["hero"]["ai_acceptance"]
    assert accept["confirmed"] == 2
