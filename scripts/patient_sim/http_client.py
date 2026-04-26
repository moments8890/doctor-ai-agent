"""Shared HTTP client helpers for demo and simulation scripts.

Provides async functions for patient registration, chat messaging,
knowledge seeding, and cleanup via the server's REST API.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Default timeout for all HTTP calls (seconds).
_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip(url: str) -> str:
    return url.rstrip("/")


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Patient registration
# ---------------------------------------------------------------------------

async def register_patient(
    server_url: str,
    doctor_id: str,
    name: str,
    gender: str,
    year_of_birth: int,
    phone: Optional[str] = None,
) -> dict:
    """Register a patient via the unified auth API.

    Returns the full response dict including ``token``, ``patient_id``,
    ``doctor_id``, ``name``.
    """
    url = f"{_strip(server_url)}/api/auth/unified/register/patient"
    payload = {
        "doctor_id": doctor_id,
        "name": name,
        "gender": gender,
        "year_of_birth": year_of_birth,
        "phone": phone or f"138{abs(hash(name)) % 100000000:08d}",
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Patient chat (triage pipeline)
# ---------------------------------------------------------------------------

async def send_patient_chat(
    server_url: str,
    patient_token: str,
    content: str,
) -> dict:
    """Send a patient chat message through the AI triage pipeline.

    Uses the ``POST /api/patient/chat`` endpoint which classifies and
    routes the message.  Returns ``{reply, triage_category, ai_handled}``.

    Parameters
    ----------
    patient_token:
        Bearer token obtained from ``register_patient``.
    """
    url = f"{_strip(server_url)}/api/patient/chat"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            json={"text": content},
            headers=_bearer(patient_token),
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Knowledge seeding
# ---------------------------------------------------------------------------

async def seed_knowledge_item(
    server_url: str,
    doctor_id: str,
    text: str,
    category: str = "custom",
    source: str = "demo",
    source_url: Optional[str] = None,
    title: Optional[str] = None,
) -> dict:
    """Seed a knowledge item via the upload/save endpoint.

    Uses ``POST /api/manage/knowledge/upload/save`` which stores the
    text with full payload metadata (source, source_url, category).
    """
    url = f"{_strip(server_url)}/api/manage/knowledge/upload/save"
    payload = {
        "text": text,
        "source_filename": source,
        "category": category,
    }
    if source_url:
        payload["source_url"] = source_url

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            json=payload,
            params={"doctor_id": doctor_id},
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

async def cleanup_demo_data(
    server_url: str,
    doctor_id_prefix: str = "demo_",
) -> dict:
    """Delete all demo data by directly cleaning the database.

    Since there is no dedicated cleanup API endpoint, this function
    connects to the database and removes rows whose ``doctor_id``
    starts with *doctor_id_prefix*.

    Returns a dict with the total number of deleted rows.
    """
    # Import here so the script can still be used without the full
    # server codebase on sys.path (falls back to error message).
    try:
        import sqlite3
        import os

        db_path = os.environ.get("DATABASE_URL", "data/doctor_agent.db")
        # Strip sqlite:/// prefix if present
        if db_path.startswith("sqlite:///"):
            db_path = db_path[len("sqlite:///"):]
        elif db_path.startswith("sqlite+aiosqlite:///"):
            db_path = db_path[len("sqlite+aiosqlite:///"):]

        tables = [
            "patient_messages",
            "doctor_tasks",
            "medical_records",
            "intake_sessions",
            "ai_suggestions",
            "patients",
            "doctor_knowledge_items",
            "doctor_contexts",
            "doctor_conversation_turns",
            "chat_archive",
            "doctors",
        ]
        total = 0
        conn = sqlite3.connect(db_path)
        try:
            for table in tables:
                try:
                    cur = conn.execute(
                        f"DELETE FROM {table} WHERE doctor_id LIKE ?",  # noqa: S608
                        (f"{doctor_id_prefix}%",),
                    )
                    total += cur.rowcount
                except sqlite3.OperationalError:
                    pass  # table may not exist
            conn.commit()
        finally:
            conn.close()

        return {"deleted_rows": total}
    except Exception as exc:
        logger.error("cleanup_demo_data failed: %s", exc)
        return {"deleted_rows": 0, "error": str(exc)}
