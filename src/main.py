"""FastAPI application entry point."""

import logging
import asyncio
import os
import sys

# Ensure src/ is on Python path (needed when invoked from project root).
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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

from fastapi import FastAPI

from db.crud import get_due_tasks
from db.engine import AsyncSessionLocal

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

from app_middleware import setup_cors, setup_exception_handlers, setup_middleware
from app_routes import include_routers, register_health_and_utility_routes
from infra.observability.request_context import install_request_context_middleware


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


def _init_sentry() -> None:
    """Initialize Sentry/GlitchTip error tracking. No-op if SENTRY_DSN is not set.

    Integrations:
    - FastApiIntegration: route-pattern transaction names (e.g.
      /doctor/review/{record_id} instead of /doctor/review/123).
    - StarletteIntegration: HTTP middleware + request breadcrumbs.
    - SqlalchemyIntegration: DB query spans on traces (slow N+1s surface).
    - LoggingIntegration: log.error() → event, log.info()/warning() →
      breadcrumbs attached to the next event.

    Release tag uses GIT_COMMIT env var (set by deploy.sh) so regressions
    can be attributed to a specific deploy.
    """
    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("ENVIRONMENT", "development"),
            release=os.environ.get("GIT_COMMIT", "unknown"),
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
            profiles_sample_rate=0.0,  # GlitchTip doesn't support profiles
            send_default_pii=False,     # strip cookies/IP, HIPAA-adjacent
            # _experimental flag enables sentry_sdk.logger.* structured logs
            # → GlitchTip Logs tab (separate from Issues). Required for the
            # observability surface to show standalone trace/info/warn events.
            _experiments={"enable_logs": True},
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR,
                ),
            ],
        )
        logging.getLogger("startup").info(
            "[Sentry] initialized (dsn=%s..., release=%s)",
            dsn[:20],
            os.environ.get("GIT_COMMIT", "unknown")[:8],
        )
    except ImportError:
        logging.getLogger("startup").warning("[Sentry] sentry-sdk not installed, skipping")


def _install_sentry_user_middleware(app) -> None:
    """Attach per-request context to Sentry events: doctor_id + role.

    Runs after auth middleware has populated request.state. No-op if
    Sentry isn't initialized.
    """
    try:
        import sentry_sdk
    except ImportError:
        return

    @app.middleware("http")
    async def _sentry_user(request, call_next):
        # Extract doctor_id from state (populated by auth middleware) or query
        doctor_id = (
            getattr(request.state, "doctor_id", None)
            or request.query_params.get("doctor_id")
        )
        if doctor_id:
            sentry_sdk.set_user({"id": doctor_id})
        sentry_sdk.set_tag("route_path", str(request.url.path))
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_ready
    _startup_log = logging.getLogger("startup")
    _init_sentry()
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


# Paths that poll frequently as a command bus — drop from uvicorn.access to
# keep logs readable. They still reach the handler and can be debugged by
# lowering the filter or logging from the route directly.
_QUIET_ACCESS_PATHS = ("/api/voice/session",)


class _QuietPathFilter:
    def filter(self, record):
        msg = record.getMessage() if hasattr(record, "getMessage") else ""
        return not any(p in msg for p in _QUIET_ACCESS_PATHS)


def _install_access_log_noise_filter() -> None:
    import logging
    logging.getLogger("uvicorn.access").addFilter(_QuietPathFilter())


def create_app() -> FastAPI:
    """Assemble and return the FastAPI application."""
    _app = FastAPI(
        title="专科医师AI智能体",
        description="Phase 2 MVP — 患者管理 + 文字录入 → 结构化病历生成",
        version="0.2.0",
        lifespan=lifespan,
    )
    _install_access_log_noise_filter()
    setup_exception_handlers(_app)
    setup_middleware(_app)
    _install_sentry_user_middleware(_app)
    install_request_context_middleware(_app)
    # NOTE on ordering: Starlette executes middleware in
    # reverse-registration order (last added = outermost). CORSMiddleware
    # is registered LAST so it is the outermost user middleware, which
    # means every response — including 500s synthesized when an
    # exception escapes a downstream BaseHTTPMiddleware (this happens
    # because BaseHTTPMiddleware's `call_next` re-raises through anyio
    # streams and bypasses ExceptionMiddleware, see starlette#919) —
    # passes through CORS on the way out. Without this, browsers see
    # a naked 5xx with no Access-Control-Allow-Origin header and
    # surface it as TypeError "Failed to fetch", which masked the
    # signal_flag schema drift on 2026-04-26.
    #
    # request_context is registered just before CORS so the request_id
    # tag is bound BEFORE the Sentry user middleware (which is inside
    # request_context) runs — preserves the original ordering rationale
    # for that middleware.
    setup_cors(_app)
    include_routers(_app)
    register_health_and_utility_routes(
        _app,
        startup_ready_fn=lambda: _startup_ready,
        bg_worker_tasks_fn=lambda: _bg_worker_tasks,
        scheduler_fn=lambda: _scheduler,
    )
    return _app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=os.environ.get("ENVIRONMENT", "").lower() in ("development", "dev"),
    )
