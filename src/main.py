"""FastAPI application entry point."""

import logging
import asyncio
import os
import sys
import time
import uuid

# Ensure src/ is on Python path (needed when invoked from project root).
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from utils.log import init_logging
from utils.app_config import AppConfig, load_config_from_json

# Must run before any module reads os.environ.
# NOTE (architectural debt): several modules (llm_client, vision, etc.) snapshot
# env vars into module-level dicts at import time.  This works because main.py
# loads config/runtime.json here before importing routers, but alternate
# entrypoints or early imports can freeze the wrong provider configuration.
# TODO: migrate to lazy provider resolution via provider_registry.resolve().
_config_source_path, _config_values = load_config_from_json()
# Env vars set externally (e.g., cli.py) take precedence over runtime.json.
# Merge: start with runtime.json values, overlay with existing env vars.
_merged_values = dict(_config_values)
for _key in list(_config_values.keys()):
    if _key in os.environ:
        _merged_values[_key] = os.environ[_key]
# Apply merged values to os.environ (so all modules see them)
for _key, _value in _merged_values.items():
    os.environ[_key] = _value
APP_CONFIG = AppConfig.from_env(env=_merged_values, env_source=str(_config_source_path))
init_logging()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy import text
from starlette.responses import Response

from channels.web.chat import router as records_router
from channels.wechat.router import router as wechat_router
from channels.web.auth import router as auth_router
from channels.web.unified_auth_routes import router as unified_auth_router
from channels.web.ui import router as ui_router
from channels.web.tasks import router as tasks_router
from channels.web.export import router as export_router
from channels.web.import_routes import router as import_router
from channels.web.patient_portal import router as patient_portal_router
from channels.web.patient_interview_routes import router as patient_interview_router
from channels.web.doctor_interview import router as doctor_interview_router
from db.engine import AsyncSessionLocal
from db.crud import get_due_tasks
from utils.errors import DomainError
from infra.observability.observability import (
    add_trace,
    reset_current_span_id,
    reset_current_trace_id,
    set_current_span_id,
    set_current_trace_id,
)

# Startup sub-modules
from startup.warmup import run_warmup
from startup.scheduler import create_scheduler, configure_scheduler
from startup.db_init import init_database, enforce_production_guards

# ---------------------------------------------------------------------------
# Layer wiring — main.py is the only file that connects channels/ <-> services/.
# ---------------------------------------------------------------------------
from channels.wechat.wechat_notify import _send_customer_service_msg
from domain.tasks.notifications import register_sender
register_sender(_send_customer_service_msg)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_scheduler = create_scheduler()
_startup_ready = False
_bg_worker_tasks: list[asyncio.Task] = []


async def _startup_background_workers() -> None:
    """Start observability writer and audit drain worker async tasks."""
    from infra.observability.observability import _disk_writer
    from infra.observability.audit import _audit_drain_worker
    _bg_worker_tasks.append(asyncio.create_task(_disk_writer(), name="disk_writer"))
    _bg_worker_tasks.append(asyncio.create_task(_audit_drain_worker(), name="audit_drain"))


async def _startup_recovery(startup_log: logging.Logger) -> None:
    """Log pending task count and re-queue crash-orphaned messages."""
    try:
        async with AsyncSessionLocal() as _session:
            _pending = await get_due_tasks(_session, datetime.now(timezone.utc))
            startup_log.info(f"[Tasks] {len(_pending)} pending unnotified task(s) at startup")
    except Exception as _e:
        startup_log.warning(f"[Tasks] startup task count failed: {_e}")
    try:
        from channels.wechat.router import recover_stale_pending_messages
        _recovered = await recover_stale_pending_messages(older_than_seconds=60)
        if _recovered:
            startup_log.info("[Recovery] re-queued stale pending_message(s) | count=%s", _recovered)
    except Exception as _e:
        startup_log.warning("[Recovery] stale pending_message recovery FAILED: %s", _e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_ready
    _startup_log = logging.getLogger("startup")
    # Production guards FIRST — before any DB/LLM/worker side effects.
    # A missing secret should abort immediately, not after tables are
    # created, prompts seeded, and workers started.
    enforce_production_guards()
    _startup_log.info("[Config] loaded environment\n%s", APP_CONFIG.to_pretty_log())
    await init_database(_startup_log)
    await run_warmup(APP_CONFIG)
    await _startup_background_workers()
    await _startup_recovery(_startup_log)
    configure_scheduler(_scheduler, _startup_log)
    _scheduler.start()
    _startup_ready = True
    yield
    _startup_ready = False
    _scheduler.shutdown()
    for task in _bg_worker_tasks:
        task.cancel()
    _bg_worker_tasks.clear()


app = FastAPI(
    title="专科医师AI智能体",
    description="Phase 2 MVP — 患者管理 + 文字录入 → 结构化病历生成",
    version="0.2.0",
    lifespan=lifespan,
)

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
    logging.getLogger("app").exception("[UnhandledError] path=%s err=%s", request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "internal_server_error"})


_MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024  # 50 MB


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
                return JSONResponse(status_code=413, content={"detail": "Request body too large"})
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
        return JSONResponse(status_code=413, content={"detail": "Request body too large"})
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


app.include_router(records_router)
app.include_router(wechat_router)
app.include_router(auth_router)
app.include_router(unified_auth_router)
app.include_router(ui_router)
app.include_router(tasks_router)
app.include_router(export_router)
app.include_router(import_router)
app.include_router(patient_portal_router)
app.include_router(patient_interview_router)
app.include_router(doctor_interview_router)


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}


@app.post("/api/test/reset-caches")
def reset_caches():
    """Clear all in-memory caches. Test/dev only."""
    import sys
    _env = os.environ.get("ENVIRONMENT", "").strip().lower()
    if _env not in ("development", "dev", "test") and "pytest" not in sys.modules:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    cleared = []

    # Agent session cache
    try:
        from agent.session import _cache, _session_ids
        _cache.clear()
        _session_ids.clear()
        cleared.append("agent_sessions")
    except ImportError:
        pass

    # Prompt loader cache
    from utils.prompt_loader import invalidate as invalidate_prompts
    invalidate_prompts()
    cleared.append("prompt_loader")

    # Rate limiter
    from infra.auth.rate_limit import _RATE_WINDOWS
    _RATE_WINDOWS.clear()
    cleared.append("rate_limit")

    return {"cleared": cleared}


@app.get("/api/version")
def api_version():
    return {"version": 1, "app_version": "0.2.0"}


# APK download — serves the latest release APK
_DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "download")

@app.get("/download/{filename}")
def download_file(filename: str):
    if not filename.endswith(".apk"):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    path = os.path.join(_DOWNLOAD_DIR, filename)
    if not os.path.realpath(path).startswith(os.path.realpath(_DOWNLOAD_DIR) + os.sep):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    if os.path.isfile(path):
        return FileResponse(path, media_type="application/vnd.android.package-archive",
                            filename=filename)
    return JSONResponse(status_code=404, content={"detail": "not found"})


# WeChat domain verification — serves any file placed in static/wechat/
# WeChat requires: GET https://yourdomain.com/<hash>.txt  → 200 OK, plain text content
_WECHAT_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "wechat")

@app.get("/{filename}.txt")
def wechat_verify(filename: str):
    path = os.path.join(_WECHAT_STATIC_DIR, f"{filename}.txt")
    # Prevent path traversal — resolved path must stay inside the static dir.
    if not os.path.realpath(path).startswith(os.path.realpath(_WECHAT_STATIC_DIR) + os.sep):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    if os.path.isfile(path):
        return FileResponse(path, media_type="text/plain")
    return JSONResponse(status_code=404, content={"detail": "not found"})


@app.get("/healthz")
async def healthz() -> Response:
    payload = await _health_snapshot()
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/readyz")
async def readyz() -> Response:
    if not _startup_ready:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    payload = await _health_snapshot()
    if payload["status"] != "ok":
        return JSONResponse(status_code=503, content={"status": "not_ready", **payload})
    return JSONResponse(status_code=200, content={"status": "ready"})


def _check_bg_workers() -> tuple[bool, list[str]]:
    """Return (all_alive, list_of_dead_worker_names)."""
    dead: list[str] = []
    for task in _bg_worker_tasks:
        if task.done():
            dead.append(task.get_name())
    return len(dead) == 0, dead


async def _health_snapshot() -> dict:
    db_ok = True
    db_error: Optional[str] = None
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)
        logging.getLogger("health").warning("[Healthz] database check failed: %s", db_error)

    scheduler_ok = bool(_scheduler.running)
    workers_ok, dead_workers = _check_bg_workers()

    all_ok = db_ok and scheduler_ok and workers_ok
    status = "ok" if all_ok else "degraded"
    payload: Dict[str, Any] = {
        "status": status,
        "checks": {
            "database": {"ok": db_ok},
            "scheduler": {"ok": scheduler_ok},
            "workers": {"ok": workers_ok},
            "startup": {"ok": bool(_startup_ready)},
        },
    }
    if db_error:
        # Don't leak raw exception details (may contain connection strings).
        payload["checks"]["database"]["error"] = "database_unavailable"
    if dead_workers:
        payload["checks"]["workers"]["dead"] = dead_workers
    return payload
