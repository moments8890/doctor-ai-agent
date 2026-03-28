"""CORS, error handlers, and HTTP middleware for the FastAPI app."""

import logging
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from utils.errors import DomainError
from infra.observability.observability import (
    add_trace,
    reset_current_span_id,
    reset_current_trace_id,
    set_current_span_id,
    set_current_trace_id,
)


def setup_cors(app: FastAPI) -> None:
    """Add CORS middleware.  Raises RuntimeError in production if origins not configured."""
    _cors_origins_raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    _cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    if not _cors_origins:
        # Default to permissive origins in development only; production must
        # configure CORS_ALLOW_ORIGINS explicitly.
        from infra.auth import is_production as _is_prod_cors
        if _is_prod_cors():
            raise RuntimeError(
                "CORS_ALLOW_ORIGINS must be set in production "
                "(comma-separated list of allowed origins). Refusing to start."
            )
        _cors_origins = ["*"]
        logging.getLogger("startup").warning(
            "[CORS] CORS_ALLOW_ORIGINS not set — defaulting to ['*'] (dev only)"
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Admin-Token", "X-Trace-Id"],
        expose_headers=["X-Trace-Id", "X-API-Version"],
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register DomainError and catch-all exception handlers."""

    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError):
        logging.getLogger("app").warning(
            "[DomainError] path=%s code=%s status=%s msg=%s context=%s",
            request.url.path,
            exc.error_code,
            exc.status_code,
            exc.message,
            exc.context,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "error_code": exc.error_code},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception):
        logging.getLogger("app").exception(
            "[UnhandledError] path=%s err=%s", request.url.path, exc
        )
        return JSONResponse(status_code=500, content={"detail": "internal_server_error"})


_MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024  # 50 MB


def setup_middleware(app: FastAPI) -> None:
    """Register HTTP middleware (body-size limiter, trace headers)."""

    @app.middleware("http")
    async def limit_request_body_middleware(request: Request, call_next):
        """Reject requests whose Content-Length exceeds the global limit.

        Checks the Content-Length header first (fast path).  For requests
        without a Content-Length (chunked transfer, missing header, or
        untrustworthy value), the actual body is measured in a streaming
        wrapper so oversize payloads are rejected before the full body is
        buffered in memory by the endpoint.
        """
        _body_too_large = False
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > _MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=413, content={"detail": "Request body too large"}
                    )
            except ValueError:
                pass
        else:
            # No Content-Length — wrap the receive channel to count bytes.
            _received = 0

            async def _counting_receive():
                nonlocal _received, _body_too_large
                message = await request.receive()
                body = message.get("body", b"")
                _received += len(body)
                if _received > _MAX_REQUEST_BODY_BYTES:
                    _body_too_large = True
                    return {"type": "http.disconnect"}
                return message

            request._receive = _counting_receive  # type: ignore[attr-defined]
        response = await call_next(request)
        if _body_too_large:
            return JSONResponse(
                status_code=413, content={"detail": "Request body too large"}
            )
        return response

    @app.middleware("http")
    async def trace_requests_middleware(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        trace_token = set_current_trace_id(trace_id)
        span_token = set_current_span_id(None)
        started_at = datetime.now(timezone.utc)
        start_clock = time.perf_counter()

        try:
            try:
                response = await call_next(request)
                status_code = int(getattr(response, "status_code", 200))
            except Exception:
                latency_ms = (time.perf_counter() - start_clock) * 1000.0
                add_trace(
                    trace_id=trace_id,
                    started_at=started_at,
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    latency_ms=latency_ms,
                )
                raise

            latency_ms = (time.perf_counter() - start_clock) * 1000.0
            add_trace(
                trace_id=trace_id,
                started_at=started_at,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=latency_ms,
            )
            if isinstance(response, Response):
                response.headers["X-Trace-Id"] = trace_id
                response.headers["X-API-Version"] = "1"
            return response
        finally:
            reset_current_span_id(span_token)
            reset_current_trace_id(trace_token)
