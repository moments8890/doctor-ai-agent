"""
Unit tests for scripts/seed_db.py — all I/O (sqlite3, file) is mocked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

import scripts.seed_db as seed_db
from scripts.seed_db import (
    export_fixture,
    import_fixture,
    main,
    reset_tables,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

PATIENT_ROW = {
    "id": 1,
    "doctor_id": "doc_001",
    "name": "李明",
    "gender": "男",
    "age": 45,
    "created_at": "2026-02-15T10:22:00",
}

RECORD_ROW = {
    "id": 7,
    "patient_id": 1,
    "doctor_id": "doc_001",
    "chief_complaint": "胸痛3小时",
    "history_of_present_illness": "患者3小时前出现胸痛",
    "past_medical_history": None,
    "physical_examination": None,
    "auxiliary_examinations": None,
    "diagnosis": "急性心肌梗死",
    "treatment_plan": None,
    "follow_up_plan": None,
    "created_at": "2026-02-15T10:30:00",
}

VALID_FIXTURE: dict = {
    "meta": {
        "exported_at": "2026-02-15T10:00:00",
        "version": 1,
        "patients_count": 1,
        "records_count": 1,
    },
    "patients": [PATIENT_ROW],
    "medical_records": [RECORD_ROW],
}


def _make_conn_mock(cursor_mock: MagicMock) -> MagicMock:
    """Return a MagicMock connection whose .cursor() returns cursor_mock."""
    conn = MagicMock()
    conn.cursor.return_value = cursor_mock
    return conn


def _fake_db_path(exists: bool = True) -> MagicMock:
    p = MagicMock(spec=Path)
    p.exists.return_value = exists
    p.__str__ = lambda self: "/fake/patients.db"
    return p


def _fake_fixture_path(content: str = "", exists: bool = True) -> MagicMock:
    p = MagicMock(spec=Path)
    p.exists.return_value = exists
    p.read_text.return_value = content
    p.parent = MagicMock()
    p.__str__ = lambda self: "/fake/tests/fixtures/seed_data.json"
    return p


# ---------------------------------------------------------------------------
# export_fixture
# ---------------------------------------------------------------------------


class TestExportFixture:
    @patch("scripts.seed_db._connect")
    def test_creates_correct_json_structure(self, mock_connect: MagicMock) -> None:
        cur = MagicMock()
        mock_connect.return_value = _make_conn_mock(cur)

        pat_exec = MagicMock()
        pat_exec.fetchall.return_value = [PATIENT_ROW]
        rec_exec = MagicMock()
        rec_exec.fetchall.return_value = [RECORD_ROW]
        cur.execute.side_effect = [pat_exec, rec_exec]

        written: dict = {}

        fixture = _fake_fixture_path()
        fixture.write_text.side_effect = lambda text, encoding: written.update(content=text)

        export_fixture(_fake_db_path(), fixture, dry_run=False)

        assert fixture.write_text.called
        payload = json.loads(written["content"])
        assert payload["meta"]["version"] == seed_db.FIXTURE_VERSION
        assert payload["meta"]["patients_count"] == 1
        assert payload["meta"]["records_count"] == 1
        assert payload["patients"][0]["name"] == "李明"
        assert payload["medical_records"][0]["chief_complaint"] == "胸痛3小时"

    @patch("scripts.seed_db._connect")
    def test_dryrun_skips_write(self, mock_connect: MagicMock) -> None:
        cur = MagicMock()
        mock_connect.return_value = _make_conn_mock(cur)

        cur.execute.return_value.fetchall.return_value = []

        fixture = _fake_fixture_path()

        export_fixture(_fake_db_path(), fixture, dry_run=True)

        fixture.write_text.assert_not_called()

    def test_missing_db_exits(self) -> None:
        db = _fake_db_path(exists=False)
        fixture = _fake_fixture_path()

        with pytest.raises(SystemExit):
            export_fixture(db, fixture)


# ---------------------------------------------------------------------------
# reset_tables
# ---------------------------------------------------------------------------


class TestResetTables:
    @patch("scripts.seed_db._connect")
    def test_issues_correct_deletes_and_sequence_reset(
        self, mock_connect: MagicMock
    ) -> None:
        cur = MagicMock()
        cur.rowcount = 0
        conn = _make_conn_mock(cur)
        mock_connect.return_value = conn

        reset_tables(_fake_db_path(), dry_run=False)

        executed_sqls = [c.args[0].strip() for c in cur.execute.call_args_list]
        assert any("DELETE FROM medical_records" in s for s in executed_sqls)
        assert any("DELETE FROM patients" in s for s in executed_sqls)
        assert any("DELETE FROM sqlite_sequence" in s for s in executed_sqls)
        assert any("patients" in s and "medical_records" in s for s in executed_sqls)
        conn.commit.assert_called_once()

    @patch("scripts.seed_db._connect")
    def test_dryrun_skips_commit(self, mock_connect: MagicMock) -> None:
        cur = MagicMock()
        conn = _make_conn_mock(cur)
        mock_connect.return_value = conn

        reset_tables(_fake_db_path(), dry_run=True)

        conn.commit.assert_not_called()
        cur.execute.assert_not_called()


# ---------------------------------------------------------------------------
# import_fixture
# ---------------------------------------------------------------------------


class TestImportFixture:
    # ------------------------------------------------------------------
    # Helper: build a cursor mock with controlled fetchone side_effects
    # ------------------------------------------------------------------

    def _import_setup(
        self,
        fixture_data: dict,
        pat_fetchone=None,
        rec_fetchone=None,
        lastrowid: int = 42,
    ):
        """
        Return (mock_connect, mock_conn, mock_cur, fixture_path_mock).

        pat_fetchone: value returned by fetchone() for the patient dedup SELECT
        rec_fetchone: value returned by fetchone() for the record dedup SELECT
        """
        cur = MagicMock()
        cur.lastrowid = lastrowid
        conn = _make_conn_mock(cur)

        # We need cursor.execute().fetchone() to return different things for
        # patient dedup (1st call) vs record dedup (Nth call).
        # Using side_effect on individual result mocks:
        pat_result = MagicMock()
        pat_result.fetchone.return_value = pat_fetchone

        rec_result = MagicMock()
        rec_result.fetchone.return_value = rec_fetchone

        # Pattern: pat_result for patient dedup, rec_result for record dedup
        # INSERT calls return a generic mock (fetchone not used there)
        insert_result = MagicMock()

        cur.execute.side_effect = [pat_result, insert_result, rec_result, insert_result]

        fixture = _fake_fixture_path(content=json.dumps(fixture_data))
        return conn, cur, fixture

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_inserts_new_patient(
        self, mock_connect: MagicMock, mock_ensure: MagicMock
    ) -> None:
        conn, cur, fixture = self._import_setup(
            VALID_FIXTURE, pat_fetchone=None, rec_fetchone=None, lastrowid=42
        )
        mock_connect.return_value = conn

        import_fixture(_fake_db_path(), fixture, dry_run=False)

        # Verify patient INSERT was issued
        insert_calls = [
            c for c in cur.execute.call_args_list if "INSERT INTO patients" in c.args[0]
        ]
        assert len(insert_calls) == 1
        # patient_id in record should be 42 (lastrowid)
        record_insert_calls = [
            c for c in cur.execute.call_args_list if "INSERT INTO medical_records" in c.args[0]
        ]
        assert len(record_insert_calls) == 1
        assert record_insert_calls[0].args[1][0] == 42  # first param = patient_id
        conn.commit.assert_called_once()

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_skips_duplicate_patient(
        self, mock_connect: MagicMock, mock_ensure: MagicMock
    ) -> None:
        # Patient SELECT returns a row → dup; expect no patient INSERT
        conn, cur, fixture = self._import_setup(
            VALID_FIXTURE, pat_fetchone=(99,), rec_fetchone=None
        )
        mock_connect.return_value = conn

        import_fixture(_fake_db_path(), fixture, dry_run=False)

        insert_calls = [
            c for c in cur.execute.call_args_list if "INSERT INTO patients" in c.args[0]
        ]
        assert len(insert_calls) == 0

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_translates_patient_id_for_records(
        self, mock_connect: MagicMock, mock_ensure: MagicMock
    ) -> None:
        conn, cur, fixture = self._import_setup(
            VALID_FIXTURE, pat_fetchone=None, rec_fetchone=None, lastrowid=77
        )
        mock_connect.return_value = conn

        import_fixture(_fake_db_path(), fixture, dry_run=False)

        rec_inserts = [
            c for c in cur.execute.call_args_list if "INSERT INTO medical_records" in c.args[0]
        ]
        assert len(rec_inserts) == 1
        # First positional param for INSERT INTO medical_records is patient_id
        assert rec_inserts[0].args[1][0] == 77

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_skips_duplicate_record(
        self, mock_connect: MagicMock, mock_ensure: MagicMock
    ) -> None:
        # Patient SELECT: dup found (existing id=99)
        # Record SELECT: dup found → should be skipped
        conn, cur, fixture = self._import_setup(
            VALID_FIXTURE, pat_fetchone=(99,), rec_fetchone=(7,)
        )
        mock_connect.return_value = conn

        import_fixture(_fake_db_path(), fixture, dry_run=False)

        rec_inserts = [
            c for c in cur.execute.call_args_list if "INSERT INTO medical_records" in c.args[0]
        ]
        assert len(rec_inserts) == 0

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_null_patient_id_in_fixture_inserts_with_null(
        self, mock_connect: MagicMock, mock_ensure: MagicMock, capsys
    ) -> None:
        """Record with patient_id=None (absent from fixture) → inserted with NULL patient_id."""
        fx = {
            "meta": {"version": 1, "patients_count": 0, "records_count": 1},
            "patients": [],
            "medical_records": [
                {**RECORD_ROW, "patient_id": None},
            ],
        }
        cur = MagicMock()
        conn = _make_conn_mock(cur)
        # Only the record dedup SELECT happens (no patient rows)
        rec_result = MagicMock()
        rec_result.fetchone.return_value = None
        insert_result = MagicMock()
        cur.execute.side_effect = [rec_result, insert_result]
        mock_connect.return_value = conn

        import_fixture(_fake_db_path(), _fake_fixture_path(content=json.dumps(fx)), dry_run=False)

        rec_inserts = [
            c for c in cur.execute.call_args_list if "INSERT INTO medical_records" in c.args[0]
        ]
        assert len(rec_inserts) == 1
        assert rec_inserts[0].args[1][0] is None  # patient_id = NULL

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_unknown_patient_id_warns(
        self, mock_connect: MagicMock, mock_ensure: MagicMock, capsys
    ) -> None:
        """Record references patient_id not in the fixture → warns and inserts with NULL."""
        fx = {
            "meta": {"version": 1, "patients_count": 0, "records_count": 1},
            "patients": [],
            "medical_records": [
                {**RECORD_ROW, "patient_id": 999},  # 999 not in id_map
            ],
        }
        cur = MagicMock()
        conn = _make_conn_mock(cur)
        rec_result = MagicMock()
        rec_result.fetchone.return_value = None
        insert_result = MagicMock()
        cur.execute.side_effect = [rec_result, insert_result]
        mock_connect.return_value = conn

        import_fixture(_fake_db_path(), _fake_fixture_path(content=json.dumps(fx)), dry_run=False)

        captured = capsys.readouterr()
        assert "999" in captured.out or "Warning" in captured.out

    def test_rejects_wrong_fixture_version(self) -> None:
        bad = {**VALID_FIXTURE, "meta": {**VALID_FIXTURE["meta"], "version": 99}}
        fixture = _fake_fixture_path(content=json.dumps(bad))

        with pytest.raises(SystemExit):
            import_fixture(_fake_db_path(), fixture)

    def test_rejects_missing_patients_key(self) -> None:
        bad = {"meta": {"version": 1}, "medical_records": []}
        fixture = _fake_fixture_path(content=json.dumps(bad))

        with pytest.raises(SystemExit):
            import_fixture(_fake_db_path(), fixture)

    def test_missing_fixture_exits(self) -> None:
        fixture = _fake_fixture_path(exists=False)

        with pytest.raises(SystemExit):
            import_fixture(_fake_db_path(), fixture)

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_dryrun_skips_commit_and_inserts(
        self, mock_connect: MagicMock, mock_ensure: MagicMock
    ) -> None:
        cur = MagicMock()
        conn = _make_conn_mock(cur)

        # Both patient and record dedup: not found
        not_found = MagicMock()
        not_found.fetchone.return_value = None
        cur.execute.side_effect = [not_found, not_found]

        mock_connect.return_value = conn

        import_fixture(_fake_db_path(), _fake_fixture_path(content=json.dumps(VALID_FIXTURE)), dry_run=True)

        conn.commit.assert_not_called()
        insert_calls = [
            c for c in cur.execute.call_args_list if "INSERT" in c.args[0]
        ]
        assert len(insert_calls) == 0

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_dryrun_reports_would_import(
        self, mock_connect: MagicMock, mock_ensure: MagicMock, capsys
    ) -> None:
        cur = MagicMock()
        conn = _make_conn_mock(cur)
        not_found = MagicMock()
        not_found.fetchone.return_value = None
        cur.execute.side_effect = [not_found, not_found]
        mock_connect.return_value = conn

        import_fixture(_fake_db_path(), _fake_fixture_path(content=json.dumps(VALID_FIXTURE)), dry_run=True)

        out = capsys.readouterr().out
        assert "dry-run" in out.lower() or "dry_run" in out.lower() or "(dry-run)" in out

    @patch("scripts.seed_db._ensure_schema")
    @patch("scripts.seed_db._connect")
    def test_rollback_on_exception(
        self, mock_connect: MagicMock, mock_ensure: MagicMock
    ) -> None:
        cur = MagicMock()
        conn = _make_conn_mock(cur)
        mock_connect.return_value = conn

        # Make execute raise on second call (INSERT)
        not_found = MagicMock()
        not_found.fetchone.return_value = None
        cur.execute.side_effect = [not_found, RuntimeError("DB error")]

        with pytest.raises(RuntimeError):
            import_fixture(_fake_db_path(), _fake_fixture_path(content=json.dumps(VALID_FIXTURE)), dry_run=False)

        conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# main() — flag routing
# ---------------------------------------------------------------------------


class TestMain:
    def _run(self, argv: list) -> None:
        with patch.object(sys, "argv", ["seed_db.py"] + argv):
            main()

    @patch("scripts.seed_db.export_fixture")
    def test_export_flag_routes_to_export(self, mock_export: MagicMock) -> None:
        self._run(["--export"])
        mock_export.assert_called_once()
        args, kwargs = mock_export.call_args
        assert args[0] == seed_db.DEFAULT_DB
        assert args[1] == seed_db.DEFAULT_FIXTURE

    @patch("scripts.seed_db.import_fixture")
    def test_import_flag_routes_to_import(self, mock_import: MagicMock) -> None:
        self._run(["--import"])
        mock_import.assert_called_once()

    @patch("scripts.seed_db.import_fixture")
    @patch("scripts.seed_db.reset_tables")
    def test_reset_then_import(
        self, mock_reset: MagicMock, mock_import: MagicMock
    ) -> None:
        self._run(["--reset", "--import"])
        mock_reset.assert_called_once()
        mock_import.assert_called_once()

    @patch("scripts.seed_db.import_fixture")
    @patch("scripts.seed_db.reset_tables")
    def test_reset_no_import(
        self, mock_reset: MagicMock, mock_import: MagicMock
    ) -> None:
        self._run(["--reset", "--no-import"])
        mock_reset.assert_called_once()
        mock_import.assert_not_called()

    @patch("scripts.seed_db.reset_tables")
    def test_reset_alone_wipes(self, mock_reset: MagicMock) -> None:
        self._run(["--reset"])
        mock_reset.assert_called_once()

    @patch("scripts.seed_db.export_fixture")
    def test_export_dryrun_passes_flag(self, mock_export: MagicMock) -> None:
        self._run(["--export", "--dry-run"])
        _, kwargs = mock_export.call_args
        # dry_run passed as positional or keyword
        all_args = list(mock_export.call_args.args) + list(mock_export.call_args.kwargs.values())
        assert True in all_args  # dry_run=True present

    def test_no_import_without_reset_errors(self) -> None:
        with pytest.raises(SystemExit):
            self._run(["--no-import"])

    def test_nothing_to_do_errors(self) -> None:
        with pytest.raises(SystemExit):
            self._run([])

    @patch("scripts.seed_db.export_fixture")
    def test_custom_db_and_fixture_paths(self, mock_export: MagicMock) -> None:
        self._run(["--export", "--db", "/tmp/my.db", "--fixture", "/tmp/fix.json"])
        args, _ = mock_export.call_args
        assert str(args[0]) == "/tmp/my.db"
        assert str(args[1]) == "/tmp/fix.json"
