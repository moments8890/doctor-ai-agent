from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

_DEFAULT_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _to_bool(raw: Optional[str], default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    return value in {"1", "true", "yes", "on"}


def _build_kv_payload(fields: Dict[str, Any]) -> str:
    parts = []
    for key in sorted(fields.keys()):
        value = fields[key]
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts)


def init_logging() -> None:
    """Initialize root logging with optional rotating file output.

    Environment variables:
    - LOG_LEVEL (default: INFO)
    - LOG_FORMAT (default: '%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    - LOG_TO_FILE (default: true)
    - LOG_DIR (default: logs)
    - LOG_FILE (default: app.log)
    - LOG_MAX_BYTES (default: 10485760)
    - LOG_BACKUP_COUNT (default: 5)
    - TASK_LOG_TO_CONSOLE (default: false)
    - SCHEDULER_LOG_TO_CONSOLE (default: false)
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = os.environ.get("LOG_FORMAT", _DEFAULT_FMT)

    root = logging.getLogger()
    root.setLevel(level)

    # Keep idempotent across repeated imports/reloads.
    for h in list(root.handlers):
        root.removeHandler(h)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(stream_handler)

    task_logger = logging.getLogger("tasks")
    task_logger.setLevel(level)
    for h in list(task_logger.handlers):
        task_logger.removeHandler(h)
    task_log_to_console = _to_bool(os.environ.get("TASK_LOG_TO_CONSOLE"), default=False)
    task_logger.propagate = task_log_to_console

    scheduler_logger = logging.getLogger("apscheduler")
    scheduler_logger.setLevel(level)
    for h in list(scheduler_logger.handlers):
        scheduler_logger.removeHandler(h)
    scheduler_log_to_console = _to_bool(
        os.environ.get("SCHEDULER_LOG_TO_CONSOLE"),
        default=False,
    )
    scheduler_logger.propagate = scheduler_log_to_console

    if _to_bool(os.environ.get("LOG_TO_FILE"), default=True):
        log_dir = Path(os.environ.get("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = os.environ.get("LOG_FILE", "app.log")
        max_bytes = int(os.environ.get("LOG_MAX_BYTES", "10485760"))
        backup_count = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

        file_handler = RotatingFileHandler(
            log_dir / log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(fmt))
        root.addHandler(file_handler)

        # Dedicated high-signal task log for scheduler/debug.
        task_file_handler = RotatingFileHandler(
            log_dir / "tasks.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        task_file_handler.setLevel(level)
        task_file_handler.setFormatter(logging.Formatter(fmt))
        task_logger.addHandler(task_file_handler)

        scheduler_file_handler = RotatingFileHandler(
            log_dir / "scheduler.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        scheduler_file_handler.setLevel(level)
        scheduler_file_handler.setFormatter(logging.Formatter(fmt))
        scheduler_logger.addHandler(scheduler_file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log(msg: str, *, logger_name: str = "app", level: str = "info", **fields: Any) -> None:
    """Backwards-compatible helper used across legacy modules."""
    logger = get_logger(logger_name)
    kv = _build_kv_payload(fields)
    payload = f"{msg} | {kv}" if kv else msg
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(payload)


def task_log(event: str, **fields: Any) -> None:
    """Structured task logger for human-readable dev debugging."""
    log(event, logger_name="tasks", **fields)
