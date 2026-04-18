"""Tests for voice session relay logic (in-memory store)."""
import time
import pytest

from channels.web.voice_jssdk import (
    _voice_sessions,
    _SESSION_TTL,
    _clean_expired_sessions,
    VoiceSessionCommand,
    post_voice_session,
    get_voice_session,
)


@pytest.fixture(autouse=True)
def clear_sessions():
    _voice_sessions.clear()
    yield
    _voice_sessions.clear()


@pytest.mark.asyncio
async def test_start_creates_session():
    resp = await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    assert resp["status"] == "pending_start"
    assert "session_id" in resp


@pytest.mark.asyncio
async def test_get_returns_pending_action():
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    resp = await get_voice_session("doc1")
    assert resp["status"] == "pending_start"
    assert resp["action"] == "start"


@pytest.mark.asyncio
async def test_stop_updates_session():
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    resp = await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="stop"))
    assert resp["status"] == "pending_stop"


@pytest.mark.asyncio
async def test_recording_updates_status():
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    resp = await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="recording"))
    assert resp["status"] == "recording"


@pytest.mark.asyncio
async def test_result_stores_transcript():
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    resp = await post_voice_session(VoiceSessionCommand(
        doctor_id="doc1", action="result", text="患者血压升高",
    ))
    assert resp["status"] == "done"

    get_resp = await get_voice_session("doc1")
    assert get_resp["text"] == "患者血压升高"
    assert get_resp["status"] == "done"


@pytest.mark.asyncio
async def test_error_stores_error():
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    resp = await post_voice_session(VoiceSessionCommand(
        doctor_id="doc1", action="error", error="permission_denied",
    ))
    assert resp["status"] == "error"

    get_resp = await get_voice_session("doc1")
    assert get_resp["error"] == "permission_denied"


@pytest.mark.asyncio
async def test_get_nonexistent_returns_idle():
    resp = await get_voice_session("nobody")
    assert resp["status"] == "idle"
    assert resp["action"] is None
    assert resp["text"] is None


@pytest.mark.asyncio
async def test_clear_resets_session():
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    resp = await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="clear"))
    assert resp["status"] == "idle"

    get_resp = await get_voice_session("doc1")
    assert get_resp["status"] == "idle"


@pytest.mark.asyncio
async def test_expired_session_returns_idle():
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    # Manually expire the session
    _voice_sessions["doc1"]["created_at"] = time.time() - _SESSION_TTL - 1
    resp = await get_voice_session("doc1")
    assert resp["status"] == "idle"


@pytest.mark.asyncio
async def test_new_start_overwrites_existing():
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    first_id = _voice_sessions["doc1"]["session_id"]
    await post_voice_session(VoiceSessionCommand(doctor_id="doc1", action="start"))
    second_id = _voice_sessions["doc1"]["session_id"]
    assert first_id != second_id
