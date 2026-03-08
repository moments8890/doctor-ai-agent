from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import db.init_db as init_db


class _SyncResult:
    def __init__(self, cols):
        self._cols = cols

    def fetchall(self):
        return [(0, col) for col in self._cols]


class _SyncConn:
    def __init__(self, table_cols):
        self._table_cols = table_cols

    def execute(self, stmt):
        sql = str(stmt)
        for table_name, cols in self._table_cols.items():
            if f"PRAGMA table_info({table_name})" in sql:
                return _SyncResult(cols)
        return _SyncResult(self._table_cols.get("patients", []))


class _AsyncConn:
    def __init__(self, table_cols):
        self.table_cols = table_cols
        self.executed_sql = []

    async def run_sync(self, fn):
        return fn(_SyncConn(self.table_cols))

    async def execute(self, stmt):
        self.executed_sql.append(str(stmt))


class _BeginCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _SessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        return _BeginCtx(self._conn)


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)


class _BackfillSession:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.added_ids = []
        self.committed = False

    async def execute(self, stmt):
        sql = str(stmt).lower()
        for table, values in self.rows_by_table.items():
            if f"from {table}" in sql:
                return _ExecResult(values)
        return _ExecResult([])

    def add(self, obj):
        self.added_ids.append(getattr(obj, "doctor_id", None))

    async def commit(self):
        self.committed = True


class _BackfillSessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


async def test_create_tables_runs_age_to_year_of_birth_migration(monkeypatch):
    conn = _AsyncConn(
        table_cols={
            "patients": ["id", "doctor_id", "name", "age"],
            "doctor_tasks": ["id", "doctor_id", "task_type", "title", "status"],
            "doctors": ["doctor_id", "name", "created_at", "updated_at"],
        }
    )
    monkeypatch.setattr(init_db, "engine", _Engine(conn))

    create_all = MagicMock()
    monkeypatch.setattr(init_db.Base.metadata, "create_all", create_all)

    await init_db.create_tables()

    create_all.assert_called_once()
    assert any("RENAME COLUMN age TO year_of_birth" in s for s in conn.executed_sql)
    assert any("ADD COLUMN channel" in s for s in conn.executed_sql)
    assert any("ADD COLUMN wechat_user_id" in s for s in conn.executed_sql)


async def test_create_tables_skips_migration_when_column_already_renamed(monkeypatch):
    conn = _AsyncConn(
        table_cols={
            "patients": [
                "id", "doctor_id", "name", "year_of_birth",
                "primary_category", "category_tags", "category_computed_at", "category_rules_version",
                "primary_risk_level", "risk_tags", "risk_score", "follow_up_state", "risk_computed_at", "risk_rules_version",
            ],
            "doctor_tasks": [
                "id", "doctor_id", "task_type", "title", "status", "trigger_source", "trigger_reason", "updated_at",
            ],
            "doctor_session_states": [
                "doctor_id", "current_patient_id", "pending_create_name", "pending_record_id", "pending_import_id",
            ],
            "doctors": ["doctor_id", "name", "channel", "wechat_user_id", "created_at", "updated_at"],
            "medical_records": [
                "id", "patient_id", "doctor_id", "content", "tags", "record_type", "created_at", "updated_at",
                "encounter_type",
            ],
            "neuro_cases": [
                "id", "doctor_id", "patient_id", "created_at", "updated_at",
            ],
            "doctor_conversation_turns": [
                "id", "doctor_id", "role", "content", "created_at", "updated_at",
            ],
        }
    )
    monkeypatch.setattr(init_db, "engine", _Engine(conn))

    create_all = MagicMock()
    monkeypatch.setattr(init_db.Base.metadata, "create_all", create_all)

    await init_db.create_tables()

    create_all.assert_called_once()
    assert conn.executed_sql == [
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_doctors_channel_wechat_user_id ON doctors(channel, wechat_user_id)"
    ]


async def test_seed_prompts_inserts_both_defaults_when_missing(monkeypatch):
    monkeypatch.setattr(init_db, "AsyncSessionLocal", lambda: _SessionCtx())
    with patch("db.crud.get_system_prompt", new=AsyncMock(side_effect=[None, None])) as get_prompt, \
         patch("db.crud.upsert_system_prompt", new=AsyncMock()) as upsert:
        await init_db.seed_prompts()

    assert get_prompt.await_count == 2
    assert upsert.await_count == 2
    first_call = upsert.await_args_list[0].args
    second_call = upsert.await_args_list[1].args
    assert first_call[1] == "structuring"
    assert second_call[1] == "structuring.neuro_cvd"


async def test_seed_prompts_is_idempotent_when_rows_exist(monkeypatch):
    monkeypatch.setattr(init_db, "AsyncSessionLocal", lambda: _SessionCtx())
    with patch("db.crud.get_system_prompt", new=AsyncMock(side_effect=[object(), object()])) as get_prompt, \
         patch("db.crud.upsert_system_prompt", new=AsyncMock()) as upsert:
        await init_db.seed_prompts()

    assert get_prompt.await_count == 2
    upsert.assert_not_awaited()


async def test_backfill_doctors_registry_inserts_missing_doctors(monkeypatch):
    session = _BackfillSession(
        {
            "patients": ["doc_a", "doc_b", "doc_a", " "],
            "medical_records": ["doc_b", "doc_c", None],
            "doctor_tasks": ["doc_d"],
            "neuro_cases": [],
            "doctor_contexts": ["doc_e"],
            "patient_labels": ["doc_f"],
            "doctors": [SimpleNamespace(doctor_id="doc_a", channel="app", wechat_user_id=None)],
        }
    )
    monkeypatch.setattr(init_db, "AsyncSessionLocal", lambda: _BackfillSessionCtx(session))

    inserted = await init_db.backfill_doctors_registry()

    assert inserted == 5
    assert set(session.added_ids) == {"doc_b", "doc_c", "doc_d", "doc_e", "doc_f"}
    assert session.committed is True


async def test_backfill_doctors_registry_noop_when_no_missing_doctors(monkeypatch):
    session = _BackfillSession(
        {
            "patients": ["doc_a", "doc_b"],
            "medical_records": [],
            "doctor_tasks": [],
            "neuro_cases": [],
            "doctor_contexts": [],
            "patient_labels": [],
            "doctors": [
                SimpleNamespace(doctor_id="doc_a", channel="app", wechat_user_id=None),
                SimpleNamespace(doctor_id="doc_b", channel="app", wechat_user_id=None),
            ],
        }
    )
    monkeypatch.setattr(init_db, "AsyncSessionLocal", lambda: _BackfillSessionCtx(session))

    inserted = await init_db.backfill_doctors_registry()

    assert inserted == 0
    assert session.added_ids == []
    assert session.committed is False


async def test_backfill_doctors_registry_sets_wechat_identity_for_existing_rows(monkeypatch):
    wx_doctor = SimpleNamespace(doctor_id="wm80GmBgAAIQojCKNChQIjEOg5VFsgGQ", channel=None, wechat_user_id=None)
    session = _BackfillSession(
        {
            "patients": [],
            "medical_records": [],
            "doctor_tasks": [],
            "neuro_cases": [],
            "doctor_contexts": [],
            "patient_labels": [],
            "doctors": [wx_doctor],
        }
    )
    monkeypatch.setattr(init_db, "AsyncSessionLocal", lambda: _BackfillSessionCtx(session))

    inserted = await init_db.backfill_doctors_registry()

    assert inserted == 0
    assert wx_doctor.channel == "wechat"
    assert wx_doctor.wechat_user_id == "wm80GmBgAAIQojCKNChQIjEOg5VFsgGQ"
    assert session.committed is True
