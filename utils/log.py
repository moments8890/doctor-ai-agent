from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

import structlog

# ---------------------------------------------------------------------------
# Request-scoped context vars — set once per incoming request, automatically
# included in every JSON log line emitted during that request.
# ---------------------------------------------------------------------------

_ctx_doctor_id: ContextVar[str] = ContextVar("doctor_id", default="")
_ctx_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_ctx_intent: ContextVar[str] = ContextVar("intent", default="")


def bind_log_context(
    *,
    doctor_id: str = "",
    trace_id: str = "",
    intent: str = "",
) -> None:
    """Bind request-scoped fields into the current async context.

    Call once at the start of each request handler.  All log records emitted
    afterwards (within the same asyncio Task) will carry these fields.
    In JSON mode they appear as separate top-level keys; in text mode they are
    appended as key=value pairs after the message.
    """
    if doctor_id:
        _ctx_doctor_id.set(doctor_id)
    if trace_id:
        _ctx_trace_id.set(trace_id)
    if intent:
        _ctx_intent.set(intent)


def clear_log_context() -> None:
    _ctx_doctor_id.set("")
    _ctx_trace_id.set("")
    _ctx_intent.set("")


# ---------------------------------------------------------------------------
# structlog processors
# ---------------------------------------------------------------------------


def _inject_context_vars(
    logger: Any, method: str, event_dict: dict
) -> dict:
    """Inject request-scoped ContextVar fields into every log event."""
    doc = _ctx_doctor_id.get("")
    tid = _ctx_trace_id.get("")
    intent = _ctx_intent.get("")
    if doc:
        event_dict.setdefault("doctor_id", doc)
    if tid:
        event_dict.setdefault("trace_id", tid)
    if intent:
        event_dict.setdefault("intent", intent)
    return event_dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_bool(raw: Optional[str], default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def init_logging() -> None:
    """Initialize logging with structlog.

    In JSON mode (LOG_JSON=true) each log line is a JSON object where every
    field passed to log() appears as a separate top-level key — queryable by
    Loki, Elasticsearch, etc.  In text mode the output is a human-readable
    timestamped line.

    Environment variables:
    - LOG_LEVEL (default: INFO)
    - LOG_JSON (default: false) — emit JSON; fields as separate keys
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
    use_json = _to_bool(os.environ.get("LOG_JSON"), default=False)

    # Processors applied before stdlib routing (shared by all handlers).
    # These build the event_dict that the final renderer turns into a string.
    pre_chain: list = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        _inject_context_vars,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        # Hand off to the stdlib ProcessorFormatter attached to each handler.
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    structlog.configure(
        processors=pre_chain,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Final rendering — JSON for machines, plain text for humans.
    if use_json:
        formatter: logging.Formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.ExceptionRenderer(),
                structlog.processors.JSONRenderer(sort_keys=False),
            ],
        )
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.ExceptionRenderer(),
                structlog.dev.ConsoleRenderer(colors=False),
            ],
        )

    # ── Root logger ──────────────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    # ── Tasks logger ─────────────────────────────────────────────────────────
    task_logger = logging.getLogger("tasks")
    task_logger.setLevel(level)
    for h in list(task_logger.handlers):
        task_logger.removeHandler(h)
    task_log_to_console = _to_bool(os.environ.get("TASK_LOG_TO_CONSOLE"), default=False)
    task_logger.propagate = task_log_to_console

    # ── Scheduler logger ─────────────────────────────────────────────────────
    scheduler_logger = logging.getLogger("apscheduler")
    scheduler_logger.setLevel(level)
    for h in list(scheduler_logger.handlers):
        scheduler_logger.removeHandler(h)
    scheduler_log_to_console = _to_bool(
        os.environ.get("SCHEDULER_LOG_TO_CONSOLE"), default=False
    )
    scheduler_logger.propagate = scheduler_log_to_console

    # ── Rotating file handlers ───────────────────────────────────────────────
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
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        task_file_handler = RotatingFileHandler(
            log_dir / "tasks.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        task_file_handler.setLevel(level)
        task_file_handler.setFormatter(formatter)
        task_logger.addHandler(task_file_handler)

        scheduler_file_handler = RotatingFileHandler(
            log_dir / "scheduler.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        scheduler_file_handler.setLevel(level)
        scheduler_file_handler.setFormatter(formatter)
        scheduler_logger.addHandler(scheduler_file_handler)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_logger(name: str) -> Any:
    """Return a structlog bound logger for the given name."""
    return structlog.get_logger(name)


def log(msg: str, *, logger_name: str = "app", level: str = "info", **fields: Any) -> None:
    """Structured log helper used across all modules.

    Fields are passed as keyword arguments and rendered as separate JSON keys
    in JSON mode (LOG_JSON=true).  None-valued fields are dropped.

    Example::

        log("dispatching", logger_name="agent", provider="deepseek", tokens=120)

    JSON output::

        {"event": "dispatching", "level": "info", "logger": "agent",
         "timestamp": "...", "provider": "deepseek", "tokens": 120}
    """
    logger = get_logger(logger_name)
    # Drop None values — avoids cluttering JSON with null fields.
    filtered = {k: v for k, v in fields.items() if v is not None}
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(msg, **filtered)


def task_log(event: str, *, level: str = "info", **fields: Any) -> None:
    """Structured task logger — routes to the dedicated tasks.log file."""
    log(event, logger_name="tasks", level=level, **fields)
