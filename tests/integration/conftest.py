"""Shared fixtures for integration tests.

All integration tests require:
  - A running server at http://127.0.0.1:8000  (uvicorn main:app --reload)
  - Ollama running at localhost:11434           (ollama serve)

Both are checked once per session; the entire integration suite is skipped
if either dependency is unavailable.
"""
import os
import sqlite3
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "patients.db"
SERVER = "http://127.0.0.1:8000"


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
        httpx.get(f"{SERVER}/", timeout=3).raise_for_status()
    except Exception:
        pytest.skip(
            "Integration tests skipped — server not running. "
            "Start with: uvicorn main:app --reload",
            allow_module_level=True,
        )


@pytest.fixture(scope="session", autouse=True)
def require_ollama():
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=3).raise_for_status()
    except Exception:
        pytest.skip(
            "Integration tests skipped — Ollama not running. "
            "Start with: ollama serve",
            allow_module_level=True,
        )


# ---------------------------------------------------------------------------
# Per-test DB cleanup — removes inttest_* rows after each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_integration_db():
    yield
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM medical_records WHERE doctor_id LIKE 'inttest_%'")
        conn.execute("DELETE FROM patients WHERE doctor_id LIKE 'inttest_%'")
        conn.execute("DELETE FROM doctor_contexts WHERE doctor_id LIKE 'inttest_%'")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def server():
    return SERVER


def chat(text, history=None, doctor_id="inttest_default", server_url=SERVER):
    # 120s to accommodate CPU-only Ollama inference in CI (routing + structuring
    # combined can take 60–90 s on a standard GitHub Actions runner).
    timeout = int(os.environ.get("CHAT_TIMEOUT", "120"))
    resp = httpx.post(
        f"{server_url}/api/records/chat",
        json={"text": text, "history": history or [], "doctor_id": doctor_id},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def db_record(doctor_id, patient_name):
    """Return (chief_complaint, diagnosis, treatment_plan) for the latest record."""
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
            "SELECT chief_complaint, diagnosis, treatment_plan "
            "FROM medical_records WHERE patient_id=? ORDER BY id DESC LIMIT 1",
            (row[0],),
        )
        return cur.fetchone()
    finally:
        conn.close()
