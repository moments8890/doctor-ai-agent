"""结构化日志初始化与辅助函数（基于 structlog）。"""
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
_ctx_layers: ContextVar[str] = ContextVar("layers", default="")
# request_id — short correlation id set by RequestContextMiddleware per
# HTTP request. Distinct from trace_id (which predates this and is used
# for internal span tracing); both are kept so we can bridge old logs.
_ctx_request_id: ContextVar[str] = ContextVar("request_id", default="")


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
    rid = _ctx_request_id.get("")
    if doc:
        event_dict.setdefault("doctor_id", doc)
    if tid:
        event_dict.setdefault("trace_id", tid)
    if intent:
        event_dict.setdefault("intent", intent)
    if rid:
        event_dict.setdefault("request_id", rid)
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


def _build_formatter(use_json: bool) -> logging.Formatter:
    """根据 LOG_JSON 配置构建 structlog ProcessorFormatter。"""
    if use_json:
        return structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.ExceptionRenderer(),
                structlog.processors.JSONRenderer(sort_keys=False),
            ],
        )
    return structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.ExceptionRenderer(),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
    )


def _configure_structlog(formatter: logging.Formatter, level: int) -> None:
    """配置 structlog 处理器链并初始化根 logger 的流处理器。"""
    pre_chain: list = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        _inject_context_vars,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]
    structlog.configure(
        processors=pre_chain,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)


def _configure_named_logger(name: str, level: int, console_env_var: str) -> logging.Logger:
    """清空并配置指定名称 logger，按环境变量决定是否 propagate 到控制台。"""
    named_logger = logging.getLogger(name)
    named_logger.setLevel(level)
    for h in list(named_logger.handlers):
        named_logger.removeHandler(h)
    named_logger.propagate = _to_bool(os.environ.get(console_env_var), default=False)
    return named_logger


def _attach_file_handlers(
    formatter: logging.Formatter,
    level: int,
    root: logging.Logger,
    task_logger: logging.Logger,
    scheduler_logger: logging.Logger,
) -> None:
    """为根 / tasks / apscheduler logger 各添加滚动文件处理器。"""
    _root = Path(__file__).resolve().parents[2]  # src/utils/log.py → project root
    log_dir = Path(os.environ.get("LOG_DIR", "")) or (_root / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = os.environ.get("LOG_FILE", "app.log")
    max_bytes = int(os.environ.get("LOG_MAX_BYTES", "10485760"))
    backup_count = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

    def _make_handler(filename: str) -> RotatingFileHandler:
        h = RotatingFileHandler(log_dir / filename, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        h.setLevel(level)
        h.setFormatter(formatter)
        return h

    root.addHandler(_make_handler(log_file))
    task_logger.addHandler(_make_handler("tasks.log"))
    scheduler_logger.addHandler(_make_handler("scheduler.log"))


def init_logging() -> None:
    """初始化 structlog 日志系统（JSON 或文本模式，可选滚动文件输出）。

    环境变量：LOG_LEVEL / LOG_JSON / LOG_TO_FILE / LOG_DIR / LOG_FILE /
    LOG_MAX_BYTES / LOG_BACKUP_COUNT / TASK_LOG_TO_CONSOLE / SCHEDULER_LOG_TO_CONSOLE。
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    use_json = _to_bool(os.environ.get("LOG_JSON"), default=False)

    console_formatter = _build_formatter(use_json)
    file_formatter = _build_formatter(use_json=True)  # always JSON for files
    _configure_structlog(console_formatter, level)

    root = logging.getLogger()
    task_logger = _configure_named_logger("tasks", level, "TASK_LOG_TO_CONSOLE")
    scheduler_logger = _configure_named_logger("apscheduler", level, "SCHEDULER_LOG_TO_CONSOLE")

    if _to_bool(os.environ.get("LOG_TO_FILE"), default=True):
        _attach_file_handlers(file_formatter, level, root, task_logger, scheduler_logger)


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
    exc_info = fields.pop("exc_info", False)
    filtered = {k: v for k, v in fields.items() if v is not None}
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(msg, exc_info=exc_info, **filtered)


def task_log(event: str, *, level: str = "info", **fields: Any) -> None:
    """Structured task logger — routes to the dedicated tasks.log file."""
    log(event, logger_name="tasks", level=level, **fields)


# ---------------------------------------------------------------------------
# Safe background task helper
# ---------------------------------------------------------------------------


def _bg_task_done_callback(task: "asyncio.Task") -> None:  # type: ignore[name-defined]
    """Log unhandled exceptions from background tasks instead of silently dropping them."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log(
            f"[bg-task] unhandled exception in {task.get_name()}: {exc}",
            level="error",
        )


def safe_create_task(coro, *, name: str | None = None) -> "asyncio.Task":  # type: ignore[name-defined]
    """Wrapper around asyncio.create_task that logs unhandled exceptions.

    Use instead of bare ``asyncio.create_task()`` for fire-and-forget background
    work to ensure failures are logged rather than silently swallowed.
    """
    import asyncio

    task = asyncio.create_task(coro, name=name)
    task.add_done_callback(_bg_task_done_callback)
    return task
