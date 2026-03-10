"""日志工具单元测试：覆盖结构化日志字段传递、文件轮转、JSON 模式输出和日志级别解析。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import utils.log as logmod


def test_log_passes_fields_as_kwargs():
    """Fields are forwarded as kwargs (separate JSON keys), not embedded in msg."""
    logger = MagicMock()
    with patch("utils.log.get_logger", return_value=logger):
        logmod.log("event", logger_name="tasks", z=2, a=1, none_val=None)

    logger.info.assert_called_once()
    call = logger.info.call_args
    # Message is the first positional arg
    assert call.args[0] == "event"
    # Non-None fields passed as kwargs (none_val is dropped)
    assert call.kwargs.get("a") == 1
    assert call.kwargs.get("z") == 2
    assert "none_val" not in call.kwargs


def test_task_log_uses_tasks_logger_name():
    logger = MagicMock()
    with patch("utils.log.get_logger", return_value=logger) as get_logger:
        logmod.task_log("tick", task_id=3)

    get_logger.assert_called_once_with("tasks")
    call = logger.info.call_args
    assert call.args[0] == "tick"
    assert call.kwargs.get("task_id") == 3


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

        def info(self, payload, **_kw):
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
    scheduler_logger = logging.getLogger("apscheduler")
    assert root.handlers
    assert tasks_logger.handlers
    assert scheduler_logger.handlers
    assert tasks_logger.propagate is False
    assert scheduler_logger.propagate is False

    # Write one log line to ensure file handlers are active.
    logmod.log("root-event", logger_name="app")
    logmod.task_log("task-event", task_id=9)
    assert (tmp_path / "dev.log").exists()
    assert (tmp_path / "tasks.log").exists()
    assert (tmp_path / "scheduler.log").exists()


def test_init_logging_tasks_can_propagate_to_console_when_enabled():
    with patch.dict(
        "os.environ",
        {
            "LOG_LEVEL": "INFO",
            "LOG_TO_FILE": "false",
            "TASK_LOG_TO_CONSOLE": "true",
        },
        clear=False,
    ):
        logmod.init_logging()

    tasks_logger = logging.getLogger("tasks")
    assert tasks_logger.propagate is True


def test_init_logging_scheduler_can_propagate_to_console_when_enabled():
    with patch.dict(
        "os.environ",
        {
            "LOG_LEVEL": "INFO",
            "LOG_TO_FILE": "false",
            "SCHEDULER_LOG_TO_CONSOLE": "true",
        },
        clear=False,
    ):
        logmod.init_logging()

    scheduler_logger = logging.getLogger("apscheduler")
    assert scheduler_logger.propagate is True


def test_json_mode_fields_are_separate_keys(tmp_path: Path):
    """In LOG_JSON=true mode, fields appear as separate JSON keys (not embedded in msg)."""
    with patch.dict(
        "os.environ",
        {
            "LOG_LEVEL": "INFO",
            "LOG_JSON": "true",
            "LOG_TO_FILE": "true",
            "LOG_DIR": str(tmp_path),
            "LOG_FILE": "app.log",
        },
        clear=False,
    ):
        logmod.init_logging()

    logmod.log("test-event", provider="deepseek", tokens=42)

    log_path = tmp_path / "app.log"
    assert log_path.exists()
    lines = [l for l in log_path.read_text().splitlines() if l.strip()]
    assert lines, "log file should have at least one line"

    # The last line should be valid JSON with separate field keys
    last = json.loads(lines[-1])
    assert last.get("event") == "test-event"
    assert last.get("provider") == "deepseek"
    assert last.get("tokens") == 42
    assert last.get("level") == "info"
