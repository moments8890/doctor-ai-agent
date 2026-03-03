from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import utils.log as logmod


def test_log_includes_sorted_kv_fields():
    logger = MagicMock()
    with patch("utils.log.get_logger", return_value=logger):
        logmod.log("event", logger_name="tasks", z=2, a=1, none_val=None)

    logger.info.assert_called_once()
    payload = logger.info.call_args.args[0]
    assert payload == "event | a=1 z=2"


def test_task_log_uses_tasks_logger_name():
    logger = MagicMock()
    with patch("utils.log.get_logger", return_value=logger) as get_logger:
        logmod.task_log("tick", task_id=3)

    get_logger.assert_called_once_with("tasks")
    payload = logger.info.call_args.args[0]
    assert "tick" in payload
    assert "task_id=3" in payload


def test_init_logging_with_console_only():
    with patch.dict(
        "os.environ",
        {
            "LOG_LEVEL": "INFO",
            "LOG_TO_FILE": "false",
        },
        clear=False,
    ):
        logmod.init_logging()


def test_to_bool_parses_false_and_default():
    assert logmod._to_bool("false", default=True) is False
    assert logmod._to_bool(None, default=False) is False


def test_log_unknown_level_falls_back_to_info():
    class _DummyLogger:
        def __init__(self):
            self.messages = []

        def info(self, payload):
            self.messages.append(payload)

    logger = _DummyLogger()
    with patch("utils.log.get_logger", return_value=logger):
        logmod.log("x", level="not_a_level")
    assert logger.messages == ["x"]


def test_init_logging_with_rotating_files(tmp_path: Path):
    with patch.dict(
        "os.environ",
        {
            "LOG_LEVEL": "INFO",
            "LOG_TO_FILE": "true",
            "LOG_DIR": str(tmp_path),
            "LOG_FILE": "dev.log",
            "LOG_MAX_BYTES": "1024",
            "LOG_BACKUP_COUNT": "2",
        },
        clear=False,
    ):
        logmod.init_logging()

    root = logging.getLogger()
    tasks_logger = logging.getLogger("tasks")
    assert root.handlers
    assert tasks_logger.handlers

    # Write one log line to ensure file handlers are active.
    logmod.log("root-event", logger_name="app")
    logmod.task_log("task-event", task_id=9)
    assert (tmp_path / "dev.log").exists()
    assert (tmp_path / "tasks.log").exists()
