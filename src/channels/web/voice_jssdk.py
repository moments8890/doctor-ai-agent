"""
Voice command-bus + legacy result relay for miniprogram ↔ web-view.

The miniprogram performs ASR on-device via the WechatSI plugin. The backend
just shuttles commands and transcripts between the web-view and the native
miniprogram page (both poll this endpoint).

Endpoints:
  POST /api/voice/session   — web-view or miniapp posts {action, text?, error?}
  GET  /api/voice/session   — either side polls to read current session state
  POST /api/voice/result    — legacy standalone voice page posts final text
  GET  /api/voice/result    — legacy retrieve-and-clear for web-view
"""
from __future__ import annotations

import time
import uuid
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["voice"])


# ── Command-bus session store ───────────────────────────────────────────────
# doctor_id → {session_id, status, action, text, error, created_at, updated_at}

_SESSION_TTL = 60.0  # seconds before a stale session is reaped
_voice_sessions: dict[str, dict] = {}


def _clean_expired_sessions() -> None:
    now = time.time()
    stale = [did for did, s in _voice_sessions.items() if now - s.get("created_at", 0) > _SESSION_TTL]
    for did in stale:
        _voice_sessions.pop(did, None)


class VoiceSessionCommand(BaseModel):
    doctor_id: str
    action: Literal["start", "stop", "recording", "interim", "result", "error", "clear"]
    text: Optional[str] = None
    error: Optional[str] = None


@router.post("/api/voice/session")
async def post_voice_session(body: VoiceSessionCommand) -> dict:
    """Update session state. Called by web-view (start/stop/clear) or miniapp
    (recording/result/error)."""
    _clean_expired_sessions()
    now = time.time()
    did = body.doctor_id
    existing = _voice_sessions.get(did)

    if body.action == "start":
        session = {
            "session_id": uuid.uuid4().hex,
            "status": "pending_start",
            "action": "start",
            "text": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        _voice_sessions[did] = session
        return {"status": "pending_start", "session_id": session["session_id"]}

    if not existing:
        # No session yet — only "start" creates one. Silently ignore others.
        return {"status": "idle"}

    if body.action == "stop":
        existing["status"] = "pending_stop"
        existing["action"] = "stop"
    elif body.action == "recording":
        existing["status"] = "recording"
        existing["action"] = None  # cleared so miniapp doesn't re-trigger start
    elif body.action == "interim":
        # Streaming interim transcript while recording is in flight. Only
        # accept while we're actually in a recording state — after stop,
        # interims get discarded so the final "result" text wins cleanly.
        if existing["status"] == "recording":
            existing["text"] = body.text or ""
    elif body.action == "result":
        existing["status"] = "done"
        existing["action"] = None
        existing["text"] = body.text or ""
    elif body.action == "error":
        existing["status"] = "error"
        existing["action"] = None
        existing["error"] = body.error or "unknown"
    elif body.action == "clear":
        _voice_sessions.pop(did, None)
        return {"status": "idle"}

    existing["updated_at"] = now
    return {"status": existing["status"]}


@router.get("/api/voice/session")
async def get_voice_session(doctor_id: str) -> dict:
    """Read current session state. Both the web-view (waiting for transcript)
    and the miniapp (waiting for a start/stop command) poll this."""
    _clean_expired_sessions()
    session = _voice_sessions.get(doctor_id)
    if not session:
        return {"status": "idle", "action": None, "text": None, "error": None}
    return {
        "status": session["status"],
        "action": session.get("action"),
        "text": session.get("text"),
        "error": session.get("error"),
    }


# ── Legacy one-shot result relay (standalone voice page) ─────────────────────
# voice/voice.js POSTs here when done; the web-view polls for the text.
# Separate from /api/voice/session (which is the bidirectional command-bus).

_voice_results: dict[str, dict] = {}


class VoiceResultStore(BaseModel):
    doctor_id: str
    text: str


@router.post("/api/voice/result")
async def store_voice_result(body: VoiceResultStore) -> dict:
    _voice_results[body.doctor_id] = {"text": body.text, "ts": time.time()}
    return {"ok": True}


@router.get("/api/voice/result")
async def get_voice_result(doctor_id: str) -> dict:
    entry = _voice_results.pop(doctor_id, None)
    if not entry or time.time() - entry["ts"] > 30:
        return {"text": None}
    return {"text": entry["text"]}
