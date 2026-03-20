"""集成测试共享 fixtures。

所有集成测试均需要：
- 运行在 http://127.0.0.1:8001 的服务器
- 运行在局域网 192.168.0.123:11434 的 Ollama（请勿使用本机 ollama）

Shared fixtures for integration tests.

All integration tests require:
  - A running server at http://127.0.0.1:8001  (uvicorn main:app --port 8001 --reload)
  - Ollama running on LAN at 192.168.0.123:11434  (do NOT use local ollama)

Both are checked once per session; the entire integration suite is skipped
if either dependency is unavailable.

Integration DB resolution:
- Prefer `PATIENTS_DB_PATH` from `config/runtime.json`.
- Fallback to repo-local `patients.db`.
This keeps DB assertions aligned with the running app configuration.
"""

import os
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
from utils.runtime_config import load_runtime_json

ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_CONFIG = load_runtime_json()
DB_PATH = Path(
    os.environ.get("PATIENTS_DB_PATH", str(_RUNTIME_CONFIG.get("PATIENTS_DB_PATH") or (ROOT / "data" / "patients.db")))
).expanduser()
SERVER = os.environ.get("INTEGRATION_SERVER_URL", "http://127.0.0.1:8001")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", str(_RUNTIME_CONFIG.get("OLLAMA_BASE_URL") or "http://192.168.0.123:11434/v1"))


def _ollama_tags_url(base_url: str) -> str:
    """Convert OpenAI-compatible Ollama base URL to /api/tags endpoint."""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return f"{root}/api/tags"


# ---------------------------------------------------------------------------
# Session-level dependency checks — skip whole suite if deps not available
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: end-to-end tests requiring a running server and Ollama",
    )


@pytest.fixture(scope="session", autouse=True)
def require_server():
    try:
        httpx.get(f"{SERVER}/", timeout=3, follow_redirects=True).raise_for_status()
    except Exception:
        pytest.skip(
            "Integration tests skipped — server not running. "
            "Start with: uvicorn main:app --port 8001 --reload",
            allow_module_level=True,
        )


@pytest.fixture(scope="session", autouse=True)
def require_ollama():
    # When routing/structuring use a cloud LLM, Ollama is only needed for
    # vision — skip this gate so text-only E2E tests can run without it.
    routing = os.environ.get("ROUTING_LLM", _RUNTIME_CONFIG.get("ROUTING_LLM", "ollama"))
    if routing != "ollama":
        return  # cloud LLM — Ollama not required
    try:
        httpx.get(_ollama_tags_url(OLLAMA_BASE_URL), timeout=3).raise_for_status()
    except Exception:
        pytest.skip(
            "Integration tests skipped — Ollama not reachable on LAN. "
            "Ensure LAN Ollama is running (do not use local ollama serve).",
            allow_module_level=True,
        )


# ---------------------------------------------------------------------------
# DB cleanup helpers
# ---------------------------------------------------------------------------

def _purge_inttest_rows(conn: sqlite3.Connection) -> None:
    """Delete all inttest_* rows from every relevant table.

    Schema-aware: skips tables that may not exist in older DB schemas.
    """
    tables_always = [
        "medical_records",
        "patients",
        "doctor_contexts",

        "doctor_conversation_turns",
        "chat_archive",
    ]
    tables_optional = ["doctor_tasks", "pending_records", "pending_messages", "interview_sessions"]

    for table in tables_always:
        try:
            conn.execute(f"DELETE FROM {table} WHERE doctor_id LIKE 'inttest_%'")
        except sqlite3.OperationalError:
            pass  # table may not exist in this schema version

    for table in tables_optional:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if exists:
            conn.execute(f"DELETE FROM {table} WHERE doctor_id LIKE 'inttest_%'")

    conn.commit()


# ---------------------------------------------------------------------------
# Session-level pre-sweep — clears debris from any previously cancelled run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def presweep_inttest_rows(require_server):
    """Wipe inttest_* rows before the suite starts.

    This ensures that data left behind by a previously cancelled/crashed run
    does not interfere with the current session.  require_server is listed as
    a dependency so we only run against a live DB, not a stale one.
    """
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        _purge_inttest_rows(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Per-test DB cleanup — removes inttest_* rows after each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_integration_db():
    """Clear server caches before each test, purge DB rows after.

    Pre-test: reset in-memory caches (dedup, prompts, rate limiter) via
    the server's /api/test/reset-caches endpoint so no state bleeds
    between test cases.

    Post-test: delete inttest_* rows from all relevant tables.
    """
    # Pre-test: clear server-side caches
    try:
        httpx.post(f"{SERVER}/api/test/reset-caches", timeout=5)
    except Exception:
        pass  # server may not support this endpoint yet

    yield

    # Post-test: purge DB rows
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        _purge_inttest_rows(conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def server():
    return SERVER


def chat(text, history=None, doctor_id="inttest_default", server_url=SERVER):
    """Call `/api/records/chat` with retry on read timeout.

    Auth note: sends doctor_id in the request body without an Authorization
    header.  This exercises the dev-only fallback path in
    ``resolve_doctor_id_from_auth_or_fallback()``, which is auto-enabled when
    ``PYTEST_CURRENT_TEST`` is set.  Production clients must send a valid
    Bearer token; see ``services/auth/request_auth.py``.
    """
    # Integration requests can be slow on shared CI runners, especially on the
    # first structured call after startup/model warmup.
    read_timeout = float(os.environ.get("CHAT_TIMEOUT", "300"))
    retries = int(os.environ.get("CHAT_RETRIES", "1"))
    timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=10.0)
    payload = {"text": text, "history": history or [], "doctor_id": doctor_id}

    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                f"{server_url}/api/records/chat",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.ReadTimeout as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(2)
                continue
            break

    raise RuntimeError(
        f"chat() timed out after {retries + 1} attempt(s); "
        f"read_timeout={read_timeout}s; doctor_id={doctor_id}"
    ) from last_exc


def db_record(doctor_id, patient_name):
    """Return (content, tags, record_type) for the latest record, or None."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM patients WHERE name=? AND doctor_id=? ORDER BY id DESC LIMIT 1",
            (patient_name, doctor_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            "SELECT content, tags, record_type "
            "FROM medical_records WHERE patient_id=? ORDER BY id DESC LIMIT 1",
            (row[0],),
        )
        return cur.fetchone()
    finally:
        conn.close()


def has_pending_draft(doctor_id):
    """Check if there's an awaiting pending record for this doctor."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT COUNT(1) FROM pending_records WHERE doctor_id=? AND status='awaiting'",
            (doctor_id,),
        ).fetchone()
        return (row[0] if row else 0) > 0
    finally:
        conn.close()


def chat_and_confirm(text, doctor_id, **kwargs):
    """Send medical text, then confirm the pending draft if one was created.

    Returns the first chat response. The confirm step ensures the record
    is persisted to medical_records via the ADR 0012 two-step flow.
    """
    data = chat(text, doctor_id=doctor_id, **kwargs)
    if data.get("record") is not None:
        return data
    if has_pending_draft(doctor_id):
        chat("确认", doctor_id=doctor_id)
    return data
