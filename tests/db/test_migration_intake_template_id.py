"""Forward + downgrade round-trip for the intake_template_id migration.

Applies every migration up to the revision under test against a fresh SQLite
DB, asserts the schema matches the spec (§4a), then downgrades one step and
asserts the change is gone.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[2]
REVISION = "c9f8d2e14a20"

# Ensure src/ is importable when alembic env.py runs inside pytest (the CLI
# prepend_sys_path=. does not fire when using the programmatic API).
_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def _alembic_cfg(db_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _prev_revision(cfg: Config) -> str:
    """Return the down_revision of REVISION (i.e. one step before it).

    Alembic's programmatic API does not support the ``^`` relative syntax that
    the CLI accepts, so we look up the parent revision explicitly.
    """
    sd = ScriptDirectory.from_config(cfg)
    script = sd.get_revision(REVISION)
    assert script is not None, f"Migration {REVISION} not found"
    return script.down_revision  # type: ignore[return-value]


@pytest.fixture()
def fresh_db(monkeypatch):
    """Yield (sync_url, path) for a fresh SQLite DB.

    env.py overrides ``sqlalchemy.url`` from ``os.environ["DATABASE_URL"]``
    (line 39 of alembic/env.py).  We must set DATABASE_URL to the
    *aiosqlite* form of the same path so that env.py's ``_to_sync_url``
    converts it back to a plain ``sqlite://`` URL pointing at our temp file,
    rather than letting env.py fall back to the project's ``patients.db``.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    sync_url = f"sqlite:///{path}"
    async_url = f"sqlite+aiosqlite:///{path}"
    monkeypatch.setenv("DATABASE_URL", async_url)
    monkeypatch.setenv("ENVIRONMENT", "test")
    yield sync_url, path
    os.unlink(path)


def test_upgrade_creates_template_id_and_form_responses(fresh_db):
    url, _ = fresh_db
    cfg = _alembic_cfg(url)

    # Start with a session row in the old schema via pre-migration upgrade
    command.upgrade(cfg, _prev_revision(cfg))  # one step before target
    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            conn.execute(text(
                "INSERT INTO doctors (doctor_id, created_at, updated_at) "
                "VALUES ('doc1', '2026-01-01', '2026-01-01')"
            ))
            conn.execute(text(
                "INSERT INTO intake_sessions (id, doctor_id, status, mode, turn_count, created_at, updated_at) "
                "VALUES ('s1', 'doc1', 'draft_created', 'doctor', 0, '2026-01-01', '2026-01-01')"
            ))

        command.upgrade(cfg, REVISION)

        insp = inspect(eng)
        session_cols = {c["name"] for c in insp.get_columns("intake_sessions")}
        assert "template_id" in session_cols

        doctor_cols = {c["name"] for c in insp.get_columns("doctors")}
        assert "preferred_template_id" in doctor_cols

        assert "form_responses" in insp.get_table_names()

        # Existing session row backfilled to medical_general_v1, status retagged
        with eng.begin() as conn:
            row = conn.execute(text(
                "SELECT template_id, status FROM intake_sessions WHERE id='s1'"
            )).first()
        assert row.template_id == "medical_general_v1"
        assert row.status == "confirmed"  # draft_created → confirmed
    finally:
        eng.dispose()


def test_downgrade_removes_everything(fresh_db):
    url, _ = fresh_db
    cfg = _alembic_cfg(url)

    # Start with a session row in the old schema before upgrade
    command.upgrade(cfg, _prev_revision(cfg))  # one step before target
    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            conn.execute(text(
                "INSERT INTO doctors (doctor_id, created_at, updated_at) "
                "VALUES ('doc1', '2026-01-01', '2026-01-01')"
            ))
            conn.execute(text(
                "INSERT INTO intake_sessions (id, doctor_id, status, mode, turn_count, created_at, updated_at) "
                "VALUES ('s1', 'doc1', 'draft_created', 'doctor', 0, '2026-01-01', '2026-01-01')"
            ))

        # Upgrade and then downgrade
        command.upgrade(cfg, REVISION)
        command.downgrade(cfg, _prev_revision(cfg))

        insp = inspect(eng)
        session_cols = {c["name"] for c in insp.get_columns("intake_sessions")}
        assert "template_id" not in session_cols
        doctor_cols = {c["name"] for c in insp.get_columns("doctors")}
        assert "preferred_template_id" not in doctor_cols
        assert "form_responses" not in insp.get_table_names()

        # Verify the data migration is irreversible: draft_created row stays confirmed
        with eng.begin() as conn:
            row = conn.execute(text(
                "SELECT status FROM intake_sessions WHERE id='s1'"
            )).first()
        assert row.status == "confirmed", (
            "Downgrade intentionally does not restore draft_created — "
            "the UPDATE in upgrade() is irreversible."
        )
    finally:
        eng.dispose()
