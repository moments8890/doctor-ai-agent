"""Request context middleware — request_id + doctor_id binding.

Attaches a short ``request_id`` (12-hex UUID4 prefix) to every incoming
HTTP request so logs, Sentry events, and the LLM call JSONL can be
correlated. The id is read from an inbound ``X-Request-Id`` header when
present (so upstream gateways/load-balancers can propagate their own
id), otherwise generated locally.

The id is stored in three places so every downstream subsystem can read
it without wiring a new argument through every function:

1. ``request.state.request_id`` — FastAPI handlers that accept ``Request``
2. ``structlog.contextvars`` — every ``log.info(...)`` in the request
   emits ``request_id=...`` automatically via the structlog processor
   chain (also written to the existing per-request ContextVars so the
   legacy ``_inject_context_vars`` processor picks it up)
3. Sentry scope tag — ``request_id`` tag on every Sentry event raised
   during the request

On the response, ``X-Request-Id`` is echoed back so the client /
operator can look up the log trail from a failed call.

Wire order matters in ``main.py``: register this middleware BEFORE the
Sentry user middleware so the ``request_id`` tag is set before Sentry
starts flattening per-request context.
"""
from __future__ import annotations

import uuid
from typing import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from utils.log import _ctx_doctor_id, _ctx_request_id


_REQUEST_ID_HEADER = "X-Request-Id"


def _new_request_id() -> str:
    """Return a 12-hex-char request id (uuid4 prefix, no dashes)."""
    return uuid.uuid4().hex[:12]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind per-request ``request_id`` + ``doctor_id`` into log/sentry scope.

    Runs once per HTTP request. Safe to install alongside the existing
    trace-id middleware — ``request_id`` is an orthogonal, stable
    correlation key; the legacy ``trace_id`` stays untouched.
    """

    async def dispatch(  # type: ignore[override]
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 1) Derive id — honor upstream if present, else mint a new one
        incoming = request.headers.get(_REQUEST_ID_HEADER, "").strip()
        request_id = incoming or _new_request_id()
        request.state.request_id = request_id

        # 2) Bind into structlog contextvars (task-local); every
        #    structlog.get_logger().info(...) call downstream sees it.
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # 3) Also populate the legacy ContextVar used by the
        #    ``_inject_context_vars`` processor — keeps the existing
        #    ``utils.log.log(...)`` helpers emitting request_id without
        #    touching every call site.
        _ctx_request_id.set(request_id)

        # 4) doctor_id, if already resolved by auth middleware, also
        #    becomes a contextvar so it lands on every log line /
        #    sentry event during this request. Most of the surface
        #    already sets _ctx_doctor_id via bind_log_context — this
        #    is a belt-and-suspenders refresh.
        doctor_id = getattr(request.state, "doctor_id", None)
        if doctor_id:
            structlog.contextvars.bind_contextvars(doctor_id=doctor_id)
            _ctx_doctor_id.set(doctor_id)

        # 5) Sentry scope tag — cheap no-op if sentry_sdk isn't init'd
        try:
            import sentry_sdk
            sentry_sdk.set_tag("request_id", request_id)
        except ImportError:
            pass

        try:
            response = await call_next(request)
        finally:
            # Unbind so the contextvars don't leak across requests in
            # workers that reuse the asyncio Task (e.g. uvicorn with
            # lifespan). structlog's unbind_contextvars accepts *keys.
            structlog.contextvars.unbind_contextvars("request_id", "doctor_id")

        # Echo back on the response so clients can trace back from
        # failures without reading server logs.
        try:
            response.headers[_REQUEST_ID_HEADER] = request_id
        except Exception:
            # Some response types (streaming, unusual custom classes)
            # may reject header mutation — never let the echo break
            # the response itself.
            pass
        return response


def install_request_context_middleware(app: FastAPI) -> None:
    """Attach :class:`RequestContextMiddleware` to ``app``.

    Call BEFORE ``_install_sentry_user_middleware`` so the ``request_id``
    tag is set before the Sentry user scope is flattened.
    """
    app.add_middleware(RequestContextMiddleware)
