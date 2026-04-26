"""Regression test fixtures.

IMPORTANT: Regression tests MUST run against port 8001 (test server), NEVER 8000 (dev server).
Port 8000 has real patient data. Start the test server with:

    PYTHONPATH=src uvicorn main:app --host 127.0.0.1 --port 8001

Run tests:

    RUN_REGRESSION=1 PYTHONPATH=src pytest tests/regression/ -v
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from uuid import uuid4
from typing import List

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]

# Resolve DB path — same pattern as tests/integration/conftest.py
try:
    from utils.runtime_config import load_runtime_json
    _RUNTIME_CONFIG = load_runtime_json()
except Exception:
    _RUNTIME_CONFIG = {}

SERVER = os.environ.get("INTEGRATION_SERVER_URL", "http://127.0.0.1:8001")

# Safety: reject port 8000 (dev server with real data)
if ":8000" in SERVER:
    raise RuntimeError(
        "REFUSED: regression tests must NOT run against port 8000 (dev server). "
        "Use port 8001: INTEGRATION_SERVER_URL=http://127.0.0.1:8001"
    )
DB_PATH = Path(
    os.environ.get(
        "PATIENTS_DB_PATH",
        str(_RUNTIME_CONFIG.get("PATIENTS_DB_PATH") or (ROOT / "data" / "patients.db")),
    )
).expanduser()

# Tripwire: regression tests assert against the live :8001 server's DB.
# If that path resolves to a protected dev DB, refuse to run so a misconfigured
# server doesn't pollute it. Mirrors the guard in tests/integration/conftest.py
# and the engine backstop in src/db/engine.py.
_PROTECTED_DEV_DB_PATHS = frozenset(
    {
        str((ROOT / "patients.db").resolve()),
        str((ROOT / "data" / "patients.db").resolve()),
    }
)
try:
    _resolved_reg_db = str(DB_PATH.resolve())
except OSError:
    _resolved_reg_db = str(DB_PATH)
if _resolved_reg_db in _PROTECTED_DEV_DB_PATHS:
    raise SystemExit(
        f"REFUSED: regression tests would target a protected dev DB:\n"
        f"  {_resolved_reg_db}\n"
        f"Start the :8001 server with PATIENTS_DB_PATH pointing at a test DB "
        f"(see docs/TESTING.md), then re-run pytest with the same env."
    )


# --- Skip guard ---


def pytest_collection_modifyitems(config, items):
    """Skip all regression tests unless RUN_REGRESSION=1."""
    if os.environ.get("RUN_REGRESSION") == "1":
        return
    skip = pytest.mark.skip(reason="Set RUN_REGRESSION=1 to run regression tests")
    for item in items:
        if "regression" in item.keywords:
            item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "regression: regression test suite")
    config.addinivalue_line("markers", "extraction: Kind A extraction tests")
    config.addinivalue_line("markers", "workflow: Kind B workflow tests")


# --- Server health check ---


@pytest.fixture(scope="session", autouse=True)
def _check_server():
    if os.environ.get("RUN_REGRESSION") != "1":
        return
    try:
        httpx.get(f"{SERVER}/docs", timeout=5)
    except httpx.ConnectError:
        pytest.skip(f"Server not reachable at {SERVER}")


# --- Fixtures ---


@pytest.fixture
def server_url():
    return SERVER


@pytest.fixture
def db_path():
    return str(DB_PATH)


class Cleanup:
    TABLES = [
        "patient_auth", "intake_sessions", "medical_records",
        "doctor_tasks", "doctor_chat_log", "doctor_knowledge_items",
        "patients", "doctors",
    ]

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.doctor_ids: List[str] = []

    def make_doctor_id(self, label: str) -> str:
        did = f"reg_{label}_{uuid4().hex[:6]}"
        self.doctor_ids.append(did)
        return did

    def track(self, doctor_id: str):
        if doctor_id not in self.doctor_ids:
            self.doctor_ids.append(doctor_id)

    def teardown(self):
        if not self.doctor_ids:
            return
        conn = sqlite3.connect(self.db_path)
        try:
            for table in self.TABLES:
                for did in self.doctor_ids:
                    try:
                        conn.execute(
                            f"DELETE FROM {table} WHERE doctor_id = ?", (did,)
                        )
                    except sqlite3.OperationalError:
                        pass
            conn.commit()
        finally:
            conn.close()


@pytest.fixture
def cleanup(db_path):
    c = Cleanup(db_path)
    yield c
    c.teardown()
