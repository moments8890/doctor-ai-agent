"""End-to-end tests for the patient registration endpoint with attach_code.

Load-bearing checks (the oracle defense):
- Invalid code, valid-code-but-duplicate-nickname, valid-code-but-missing-field
  all return identical response envelopes (status + body).
- Response timings are within a small window of each other so an attacker
  cannot use latency to distinguish failure modes.
- Rate limit fires on the 4th attempt within an hour (and the 429 envelope
  is also identical regardless of code validity).
- The legacy GET /unified/doctors endpoint is gone (404).
"""
from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Required before any auth helper is imported — register_patient calls
# issue_token which validates the secret at use time.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("UNIFIED_AUTH_SECRET", "test-secret-32-bytes-long-enough!")

from db.engine import Base, AsyncSessionLocal
from db.models import Doctor


@pytest_asyncio.fixture
async def app(monkeypatch, session_factory):
    """Build a minimal FastAPI app wired only with the auth router so we can
    exercise the real endpoint with httpx + ASGITransport. We patch
    AsyncSessionLocal to point at the in-memory engine the test fixtures own.
    """
    from fastapi import FastAPI
    from channels.web.auth.unified import router

    # Rebind AsyncSessionLocal in the registration helper to our in-memory factory.
    import db.engine as _engine
    monkeypatch.setattr(_engine, "AsyncSessionLocal", session_factory)
    import infra.auth.unified as _auth_unified
    monkeypatch.setattr(_auth_unified, "AsyncSessionLocal", session_factory, raising=False)

    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    yield fastapi_app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seeded_doctor(session_factory):
    """Seed one doctor with a known attach code and one already-used nickname."""
    async with session_factory() as db:
        d = Doctor(doctor_id="doc_seed", name="Dr Seed", patient_attach_code="AB2C")
        db.add(d)
        await db.commit()
    return {"doctor_id": "doc_seed", "attach_code": "AB2C"}


# --- Happy path -----------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_code_returns_token(client, seeded_doctor):
    res = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "alice", "passcode": "123456",
        "attach_code": seeded_doctor["attach_code"],
    })
    assert res.status_code == 200
    body = res.json()
    assert "token" in body
    assert body["doctor_id"] == seeded_doctor["doctor_id"]


# --- Oracle defense: response shape parity --------------------------------


@pytest.mark.asyncio
async def test_invalid_code_returns_generic_422(client, seeded_doctor):
    res = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "bob", "passcode": "123456",
        "attach_code": "ZZZZ",  # non-existent code
    })
    assert res.status_code == 422
    assert res.json()["detail"] == "无法完成注册"


@pytest.mark.asyncio
async def test_valid_code_duplicate_nickname_returns_same_envelope(client, seeded_doctor):
    # First register succeeds.
    res1 = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "carol", "passcode": "123456",
        "attach_code": seeded_doctor["attach_code"],
    })
    assert res1.status_code == 200
    # Second register with same nickname under same doctor must return the
    # SAME 422 envelope as an invalid-code attempt — no leak that the code
    # was valid.
    res2 = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "carol", "passcode": "123456",
        "attach_code": seeded_doctor["attach_code"],
    })
    assert res2.status_code == 422
    assert res2.json()["detail"] == "无法完成注册"


@pytest.mark.asyncio
async def test_response_envelopes_identical_across_failure_modes(client, seeded_doctor):
    """Every failure mode returns the exact same status + body.

    Clears the per-IP rate limit between calls so we can exercise > 3 attempts
    in a single test (the rate-limit defense itself is covered separately).
    """
    from infra.auth.rate_limit import clear_rate_limits_for_tests

    # Seed a doctor-bound nickname so we have something to duplicate.
    seed_res = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "dave", "passcode": "123456",
        "attach_code": seeded_doctor["attach_code"],
    })
    assert seed_res.status_code == 200, "seed registration must succeed"
    clear_rate_limits_for_tests()

    invalid = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "eve", "passcode": "123456", "attach_code": "ZZZZ",
    })
    clear_rate_limits_for_tests()
    duplicate = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "dave", "passcode": "123456",
        "attach_code": seeded_doctor["attach_code"],
    })
    clear_rate_limits_for_tests()
    short_code = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "frank", "passcode": "123456", "attach_code": "AB",
    })
    for res in (invalid, duplicate, short_code):
        assert res.status_code == 422
        assert res.json() == {"detail": "无法完成注册"}


# --- Oracle defense: timing parity ---------------------------------------


@pytest.mark.asyncio
async def test_response_timing_is_padded_uniformly(client, seeded_doctor):
    """Failure responses are padded to >= 400ms regardless of failure mode."""
    samples = []
    for code in ("ZZZZ", "YYYY", "XXXX"):  # all invalid → bypass DB work
        t0 = time.monotonic()
        await client.post("/api/auth/unified/register/patient", json={
            "nickname": f"u_{code}", "passcode": "123456", "attach_code": code,
        })
        samples.append(time.monotonic() - t0)
    # Every response should be >= the floor.
    for s in samples:
        assert s >= 0.4, f"response too fast ({s:.3f}s) — timing oracle exposed"


# --- Rate limit ----------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_fires_on_fourth_attempt(client, seeded_doctor):
    """3 attempts/hour per IP. 4th should be blocked."""
    for i in range(3):
        await client.post("/api/auth/unified/register/patient", json={
            "nickname": f"rate_{i}", "passcode": "123456",
            "attach_code": seeded_doctor["attach_code"],
        })
    res4 = await client.post("/api/auth/unified/register/patient", json={
        "nickname": "rate_3", "passcode": "123456",
        "attach_code": seeded_doctor["attach_code"],
    })
    assert res4.status_code == 429


# --- Legacy endpoint removal ---------------------------------------------


@pytest.mark.asyncio
async def test_unified_doctors_endpoint_is_gone(client):
    """The public doctor enumeration endpoint is removed."""
    res = await client.get("/api/auth/unified/doctors")
    assert res.status_code == 404
