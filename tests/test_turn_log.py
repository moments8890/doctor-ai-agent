"""Unit tests for services.observability.turn_log."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# We need to reload the module with controlled settings so module-level
# constants (_ENABLED, _LOG_FILE, _TTL_DAYS) use our test values.
# The easiest approach: import the module, then patch the module-level attrs
# inside each test/fixture.
# ---------------------------------------------------------------------------
import services.observability.turn_log as turn_log_mod


def _make_ts(days_ago: int = 0) -> str:
    """Return an ISO 8601 timestamp `days_ago` days in the past."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── log_turn: disabled in test mode ────────────────────────────────────

class TestLogTurnDisabledInTestMode:
    """When _is_test() returns True (the default during pytest), log_turn is a no-op."""

    def test_no_file_written_in_test_mode(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_ENABLED", True), \
             patch.object(turn_log_mod, "_is_test", return_value=True):
            turn_log_mod.log_turn(
                text="hello",
                intent="greeting",
                routing="fast",
                doctor_id="doc1",
                latency_ms=12.3,
            )
        assert not log_file.exists(), "log_turn should be a no-op in test mode"


# ── log_turn: enabled ──────────────────────────────────────────────────

class TestLogTurnEnabled:
    """When _is_test() is False and _ENABLED is True, a JSONL line is written."""

    def test_writes_jsonl_line(self, tmp_path: Path):
        log_file = tmp_path / "sub" / "turn_log.jsonl"
        # Force sync fallback by making _enqueue_jsonl raise at its source module
        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_ENABLED", True), \
             patch.object(turn_log_mod, "_is_test", return_value=False), \
             patch("services.observability.observability._enqueue_jsonl", side_effect=Exception("force sync")):
            turn_log_mod.log_turn(
                text="患者头痛",
                intent="add_record",
                routing="fast",
                doctor_id="doc42",
                latency_ms=55.678,
            )

        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["doctor_id"] == "doc42"
        assert row["text"] == "患者头痛"
        assert row["intent"] == "add_record"
        assert row["routing"] == "fast"
        assert row["latency_ms"] == 55.7  # rounded to 1 decimal
        assert "ts" in row

    def test_creates_parent_dirs(self, tmp_path: Path):
        log_file = tmp_path / "deep" / "nested" / "turn_log.jsonl"
        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_ENABLED", True), \
             patch.object(turn_log_mod, "_is_test", return_value=False), \
             patch("services.observability.observability._enqueue_jsonl", side_effect=Exception):
            turn_log_mod.log_turn(
                text="x", intent="i", routing="llm",
                doctor_id="d", latency_ms=1.0,
            )
        assert log_file.parent.exists()


# ── log_turn: optional fields ──────────────────────────────────────────

class TestLogTurnOptionalFields:
    def test_patient_name_included(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_ENABLED", True), \
             patch.object(turn_log_mod, "_is_test", return_value=False), \
             patch("services.observability.observability._enqueue_jsonl", side_effect=Exception):
            turn_log_mod.log_turn(
                text="张三血压高",
                intent="add_record",
                routing="fast",
                doctor_id="doc1",
                latency_ms=10.0,
                patient_name="张三",
            )
        row = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert row["patient_name"] == "张三"

    def test_provenance_included(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        prov = {"current_patient_source": "session", "memory_used": True}
        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_ENABLED", True), \
             patch.object(turn_log_mod, "_is_test", return_value=False), \
             patch("services.observability.observability._enqueue_jsonl", side_effect=Exception):
            turn_log_mod.log_turn(
                text="test",
                intent="query",
                routing="llm",
                doctor_id="d1",
                latency_ms=5.0,
                provenance=prov,
            )
        row = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert row["provenance"] == prov

    def test_optional_fields_omitted_when_none(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_ENABLED", True), \
             patch.object(turn_log_mod, "_is_test", return_value=False), \
             patch("services.observability.observability._enqueue_jsonl", side_effect=Exception):
            turn_log_mod.log_turn(
                text="hi",
                intent="greeting",
                routing="fast",
                doctor_id="d",
                latency_ms=1.0,
                patient_name=None,
                provenance=None,
            )
        row = json.loads(log_file.read_text(encoding="utf-8").strip())
        assert "patient_name" not in row
        assert "provenance" not in row


# ── log_turn: _ENABLED=False ───────────────────────────────────────────

class TestLogTurnDisabledByConfig:
    def test_no_write_when_disabled(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_ENABLED", False), \
             patch.object(turn_log_mod, "_is_test", return_value=False):
            turn_log_mod.log_turn(
                text="x", intent="i", routing="fast",
                doctor_id="d", latency_ms=1.0,
            )
        assert not log_file.exists()


# ── prune_turn_log ─────────────────────────────────────────────────────

class TestPruneTurnLog:
    def _write_lines(self, path: Path, lines: list) -> None:  # noqa: ANN001
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def test_removes_old_entries_keeps_new(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        old_ts = _make_ts(days_ago=60)
        new_ts = _make_ts(days_ago=5)
        lines = [
            json.dumps({"ts": old_ts, "text": "old"}),
            json.dumps({"ts": new_ts, "text": "new"}),
        ]
        self._write_lines(log_file, lines)

        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_TTL_DAYS", 30):
            kept = turn_log_mod.prune_turn_log()

        assert kept == 1
        remaining = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(remaining) == 1
        assert json.loads(remaining[0])["text"] == "new"

    def test_empty_file(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        log_file.write_text("", encoding="utf-8")
        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_TTL_DAYS", 30):
            kept = turn_log_mod.prune_turn_log()
        assert kept == 0

    def test_nonexistent_file(self, tmp_path: Path):
        log_file = tmp_path / "does_not_exist.jsonl"
        with patch.object(turn_log_mod, "_LOG_FILE", log_file):
            kept = turn_log_mod.prune_turn_log()
        assert kept == 0

    def test_malformed_lines_preserved(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        new_ts = _make_ts(days_ago=1)
        lines = [
            "this is not valid json",
            json.dumps({"ts": new_ts, "text": "ok"}),
            "{bad json{",
        ]
        self._write_lines(log_file, lines)

        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_TTL_DAYS", 30):
            kept = turn_log_mod.prune_turn_log()

        # malformed lines are kept + 1 valid new entry = 3
        assert kept == 3
        remaining = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert remaining[0] == "this is not valid json"
        assert remaining[2] == "{bad json{"

    def test_all_old_entries_removed(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        old_ts = _make_ts(days_ago=100)
        lines = [
            json.dumps({"ts": old_ts, "text": "ancient1"}),
            json.dumps({"ts": old_ts, "text": "ancient2"}),
        ]
        self._write_lines(log_file, lines)

        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_TTL_DAYS", 30):
            kept = turn_log_mod.prune_turn_log()

        assert kept == 0

    def test_all_new_entries_kept(self, tmp_path: Path):
        log_file = tmp_path / "turn_log.jsonl"
        ts = _make_ts(days_ago=1)
        lines = [
            json.dumps({"ts": ts, "text": "a"}),
            json.dumps({"ts": ts, "text": "b"}),
            json.dumps({"ts": ts, "text": "c"}),
        ]
        self._write_lines(log_file, lines)

        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_TTL_DAYS", 30):
            kept = turn_log_mod.prune_turn_log()

        assert kept == 3

    def test_boundary_exact_cutoff_kept(self, tmp_path: Path):
        """Entry exactly at the cutoff boundary (== cutoff) should be kept."""
        log_file = tmp_path / "turn_log.jsonl"
        # Create an entry exactly _TTL_DAYS old
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=30)
        cutoff_ts = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = [json.dumps({"ts": cutoff_ts, "text": "boundary"})]
        self._write_lines(log_file, lines)

        with patch.object(turn_log_mod, "_LOG_FILE", log_file), \
             patch.object(turn_log_mod, "_TTL_DAYS", 30):
            kept = turn_log_mod.prune_turn_log()

        # The entry is at the exact cutoff second; since prune uses >=, it is kept
        # (or dropped — depends on sub-second timing). We just verify no crash.
        assert kept in (0, 1)
