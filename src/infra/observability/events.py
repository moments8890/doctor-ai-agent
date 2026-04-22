"""Business-event logging helper.

Fan-out wrapper: every ``log_event`` call lands in two places —

1. ``logs/app.log`` via structlog (searchable locally, survives Sentry
   outage, included in support bundle)
2. Sentry (GlitchTip) Logs tab via ``sentry_sdk.logger.info`` — only
   active when ``_experiments={"enable_logs": True}`` is set on
   ``sentry_sdk.init`` (see ``_init_sentry`` in ``main.py``)

Every log line inherits the current structlog contextvars — notably
``request_id``, ``doctor_id``, and ``trace_id`` — so biz events can be
joined against HTTP access logs and LLM call records without extra work
at each call site.

PII policy: callers must pass IDs, counts, durations, enum values, and
booleans only. No patient names, no raw message text, no draft bodies.
This is enforced by convention — we do not filter here because the
caller knows the shape of the payload.
"""
from __future__ import annotations

from typing import Any

import structlog

_log = structlog.get_logger("biz")


def log_event(event_name: str, **attrs: Any) -> None:
    """Emit a business event to structlog + Sentry Logs.

    ``event_name`` should be a short dotted identifier
    (``record.finalized``, ``draft.sent``, etc.) so events can be
    grouped by prefix in downstream tooling.

    Unknown/None attrs are forwarded as-is; structlog drops None
    implicitly when LOG_JSON=true. Keep payload small and type-safe.
    """
    # Local structlog — preserves contextvars (request_id etc.)
    _log.info(event_name, **attrs)

    # Sentry Logs — only works when _experiments.enable_logs=True in init.
    # Wrapped in try/except because sentry_sdk.logger is still an
    # _experimental API; a version bump could rename it.
    try:
        from sentry_sdk import logger as _sentry_log
        _sentry_log.info("biz.{event}", event=event_name, **attrs)
    except Exception:
        # Never block a business-event emit on observability plumbing.
        pass
