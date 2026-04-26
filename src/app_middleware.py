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
        # X-Client-Channel: api.js sets this to "miniapp" when running inside
        # the WeChat Mini Program web-view (window.__wxjs_environment check).
        # Omitting it here was making every authenticated cross-origin call
        # from the webview fail at the CORS preflight (login worked because
        # unifiedLogin calls fetch directly, not through the request wrapper
        # that adds the header).
        allow_headers=[
            "Authorization", "Content-Type",
            "X-Admin-Token", "X-Trace-Id", "X-Client-Channel",
        ],
        expose_headers=["X-Trace-Id", "X-API-Version"],
        # iOS WKWebView (Capacitor builds, iOS 17+) sends
        # `Access-Control-Request-Private-Network: true` on cross-origin
        # preflights. Without this flag, Starlette's CORSMiddleware returns
        # 400 "Disallowed CORS private-network" and every API call from the
        # native iOS app fails with "load failed".
        allow_private_network=True,
    )


_EXC_BODY_MAX_BYTES = 2 * 1024  # 2 KB — Sentry context attachment cap
# Content-types where attaching the raw body is pointless (binary /
# huge) and actively harmful (PDF uploads, image data, audio clips).
_EXC_BODY_SKIP_PREFIXES = (
    "multipart/",
    "application/octet-stream",
    "application/pdf",
    "image/",
    "audio/",
    "video/",
)

# Allowlist of JSON keys safe to retain in error telemetry. Everything else
# is replaced with "<redacted>". An allowlist (rather than denylist) means
# new endpoints don't silently leak PII just because their field names
# weren't on a list someone forgot to update.
#
# Add a key here only after confirming its values are NOT user-controlled
# free text and NOT a credential / identifier the operator wouldn't want
# in an exception trace. When in doubt, keep the key OFF the list.
_EXC_BODY_SAFE_KEYS = frozenset({
    # Status / control flags
    "ok", "status", "decision", "role", "kind", "type", "method",
    "category", "intent", "section", "direction", "source",
    # Pagination + filters
    "limit", "offset", "page", "per_page", "since", "before", "after",
    # Synthetic IDs (random tokens, not PII). Excluded by design:
    #   - invite_code: a registration credential. Keep redacted.
    #   - session_id: used as patient-portal auth in some flows.
    #   - access_code: same.
    "id", "task_id", "record_id", "doctor_id", "patient_id",
    "suggestion_id", "template_id", "edit_id",
    "request_id", "trace_id",
    # Booleans + counters from response shapes
    "has_more", "total", "count", "ok_count", "err_count",
    # Versioning fields
    "version", "schema_version", "migration",
})


def _redact_pii_in_json(text: str) -> str:
    """Return a JSON string with non-allowlisted values replaced by "<redacted>".

    Allowlist semantics: only keys explicitly listed in _EXC_BODY_SAFE_KEYS
    keep their values; everything else is redacted. Recurse into dicts to
    catch nested user content. Lists pass through (we don't redact list
    elements unless they themselves are dicts, which then get walked).

    Best-effort: if the body isn't valid JSON, returns the original string
    (still bounded by the caller's max-bytes cap).
    """
    import json
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return text

    def _walk(node):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                key_lc = k.lower() if isinstance(k, str) else ""
                if key_lc in _EXC_BODY_SAFE_KEYS:
                    out[k] = _walk(v)  # safe key — keep value, but recurse
                else:
                    out[k] = "<redacted>"
            return out
        if isinstance(node, list):
            return [_walk(x) for x in node]
        return node

    try:
        return json.dumps(_walk(obj), ensure_ascii=False)
    except (TypeError, ValueError):
        return text


async def _capture_request_body_for_sentry(request: Request) -> None:
    """Attach truncated request body to Sentry scope.

    Idempotent — reads ``request.body()`` once (Starlette caches the
    result internally on the ASGI receive channel), so subsequent
    handler code still gets the body. Binary / multipart payloads are
    skipped with a placeholder marker instead of being serialized.
    Sensitive JSON keys (patient names, passcodes, free-text clinical
    content) are redacted before the body lands in Sentry — see
    ``_EXC_BODY_REDACT_KEYS`` above.

    Never raises — observability must not break the error path.
    """
    try:
        import sentry_sdk
    except ImportError:
        return

    content_type = (request.headers.get("content-type") or "").lower()
    if any(content_type.startswith(p) for p in _EXC_BODY_SKIP_PREFIXES):
        sentry_sdk.set_context(
            "request_body",
            {"note": "<binary, skipped>", "content_type": content_type},
        )
        return

    try:
        raw = await request.body()
    except Exception:
        # Body may already be consumed (e.g. streaming upload) or the
        # ASGI receive channel may be closed. Don't let this abort the
        # handler chain.
        return

    if not raw:
        return

    truncated = raw[:_EXC_BODY_MAX_BYTES]
    try:
        text = truncated.decode("utf-8", errors="replace")
    except Exception:
        text = repr(truncated)

    # Redact PII keys when the body looks like JSON. Non-JSON bodies
    # pass through unchanged — they'd be form-urlencoded or plain text
    # and rarely carry PHI in this app.
    if "json" in content_type or text.lstrip().startswith(("{", "[")):
        text = _redact_pii_in_json(text)

    sentry_sdk.set_context(
        "request_body",
        {
            "text": text,
            "truncated": len(raw) > _EXC_BODY_MAX_BYTES,
            "total_bytes": len(raw),
            "content_type": content_type,
        },
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
        # Attach request body to Sentry context BEFORE logging.exception
        # — the LoggingIntegration turns log.exception into a Sentry
        # event, so the context has to be on the scope first.
        await _capture_request_body_for_sentry(request)
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
            except Exception as exc:
                # Convert the exception into a 500 Response here rather than
                # re-raising. Re-raising lets the exception escape past
                # CORSMiddleware (which sits inside this middleware in the
                # ASGI stack), so the response synthesized by Starlette's
                # outer ServerErrorMiddleware lands at the client without
                # CORS headers. The browser then surfaces it as a generic
                # "Failed to fetch" instead of the real 500, which is what
                # masked the signal_flag schema drift on 2026-04-26.
                logging.getLogger("app").exception(
                    "[UnhandledError] path=%s err=%s", request.url.path, exc
                )
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "internal_server_error"},
                )
                status_code = 500

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
