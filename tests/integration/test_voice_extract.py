"""Integration tests for POST /api/manage/knowledge/voice-extract.

These tests run in-process using an ASGITransport client so that
unittest.mock.patch can intercept the ASR and LLM calls.  They do NOT
require a running external server.

The ``require_server`` and ``require_ollama`` fixtures from the
integration conftest are overridden below so that these tests can run
standalone without a live dev server.
"""
from __future__ import annotations

import os
import pathlib
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from db.engine import Base, get_db
from channels.web.doctor_dashboard.knowledge_handlers import router as _knowledge_router


FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "audio"


# ---------------------------------------------------------------------------
# Override session-scoped integration guards — these tests are in-process
# and do not require a running dev server or LAN Ollama.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def require_server():  # noqa: F811 — intentionally shadows conftest fixture
    """No-op override: in-process tests don't need the dev server."""
    return


@pytest.fixture(autouse=True)
def require_ollama():  # noqa: F811 — intentionally shadows conftest fixture
    """No-op override: LLM is mocked, Ollama not needed."""
    return


@pytest.fixture(autouse=True)
def presweep_inttest_rows():  # noqa: F811
    """No-op override: no live DB to sweep."""
    return


@pytest.fixture(autouse=True)
def clean_integration_db():  # noqa: F811
    """No-op override: in-memory DB, nothing to clean."""
    return


# ---------------------------------------------------------------------------
# Minimal in-process app fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def _test_engine():
    """In-memory SQLite engine for the test session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def async_client(_test_engine):
    """httpx AsyncClient wired to a minimal in-process FastAPI app."""
    _Session = async_sessionmaker(_test_engine, expire_on_commit=False)

    async def _override_get_db():
        async with _Session() as session:
            yield session

    app = FastAPI()
    app.include_router(_knowledge_router)
    app.dependency_overrides[get_db] = _override_get_db

    # Ensure dev auth fallback is active (non-production env)
    os.environ.setdefault("ENVIRONMENT", "development")
    # Use a non-browser ASR provider so the handler doesn't immediately 400
    os.environ["ASR_PROVIDER"] = "tencent"

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture(scope="module")
def authed_doctor_id():
    return "test_doctor_1"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_voice_extract_empty_file(async_client, authed_doctor_id):
    """Empty upload returns audio_unclear."""
    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers.get_asr_provider",
        return_value=__import__(
            "services.asr.provider", fromlist=["ASRProvider"]
        ).ASRProvider.tencent,
    ):
        files = {"file": ("empty.mp3", b"", "audio/mpeg")}
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files=files,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] == "audio_unclear"
    assert body["candidate"] is None


async def test_voice_extract_happy_path(async_client, authed_doctor_id):
    audio = (FIXTURES / "short_tone.mp3").read_bytes()

    class _FakeLLM:
        def __init__(self):
            self.content = "术后第三天拆线"
            self.category = "followup"
            self.error = None

    from services.asr.provider import ASRProvider

    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers.get_asr_provider",
        return_value=ASRProvider.tencent,
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers.transcribe_audio_bytes",
        new=AsyncMock(return_value="术后第三天拆线"),
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=_FakeLLM()),
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("rec.mp3", audio, "audio/mpeg")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["candidate"]["content"] == "术后第三天拆线"
    assert body["candidate"]["category"] == "followup"


async def test_voice_extract_no_rule_found(async_client, authed_doctor_id):
    audio = (FIXTURES / "short_tone.mp3").read_bytes()

    class _FakeLLM:
        content = None
        category = None
        error = "no_rule_found"

    from services.asr.provider import ASRProvider

    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers.get_asr_provider",
        return_value=ASRProvider.tencent,
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers.transcribe_audio_bytes",
        new=AsyncMock(return_value="今天天气不错"),
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=_FakeLLM()),
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("rec.mp3", audio, "audio/mpeg")},
        )
    assert resp.status_code == 200
    assert resp.json()["error"] == "no_rule_found"


async def test_voice_extract_multi_rule(async_client, authed_doctor_id):
    audio = (FIXTURES / "short_tone.mp3").read_bytes()

    class _FakeLLM:
        content = None
        category = None
        error = "multi_rule_detected"

    from services.asr.provider import ASRProvider

    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers.get_asr_provider",
        return_value=ASRProvider.tencent,
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers.transcribe_audio_bytes",
        new=AsyncMock(return_value="规则一 规则二"),
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=_FakeLLM()),
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("rec.mp3", audio, "audio/mpeg")},
        )
    assert resp.status_code == 200
    assert resp.json()["error"] == "multi_rule_detected"


async def test_voice_extract_oversize_returns_too_long(async_client, authed_doctor_id):
    from services.asr.provider import ASRProvider

    big = b"\x00" * (11 * 1024 * 1024)  # 11 MB
    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers.get_asr_provider",
        return_value=ASRProvider.tencent,
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("big.mp3", big, "audio/mpeg")},
        )
    assert resp.status_code == 200
    assert resp.json()["error"] == "too_long"


async def test_voice_extract_asr_failure_returns_502(async_client, authed_doctor_id):
    audio = (FIXTURES / "short_tone.mp3").read_bytes()

    from services.asr.provider import ASRProvider

    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers.get_asr_provider",
        return_value=ASRProvider.tencent,
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers.transcribe_audio_bytes",
        new=AsyncMock(side_effect=RuntimeError("tencent down")),
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("rec.mp3", audio, "audio/mpeg")},
        )
    assert resp.status_code == 502
