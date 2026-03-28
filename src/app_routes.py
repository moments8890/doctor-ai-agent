"""Router registrations and app-level HTTP endpoints."""

import os
import sys
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
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


# ---------------------------------------------------------------------------
# Static file directories (resolved relative to this file, which lives in src/)
# ---------------------------------------------------------------------------
_DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "download")
_WECHAT_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "wechat")


def include_routers(app: FastAPI) -> None:
    """Register all channel routers on the app."""
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


def register_health_and_utility_routes(
    app: FastAPI,
    startup_ready_fn,
    bg_worker_tasks_fn,
    scheduler_fn,
) -> None:
    """Register health, utility, and static-file endpoints.

    Parameters
    ----------
    startup_ready_fn:
        Zero-arg callable that returns the current ``_startup_ready`` bool.
    bg_worker_tasks_fn:
        Zero-arg callable that returns the current ``_bg_worker_tasks`` list.
    scheduler_fn:
        Zero-arg callable that returns the APScheduler instance.
    """

    @app.get("/")
    def root():
        return {"status": "ok", "docs": "/docs"}

    @app.post("/api/test/reset-caches")
    def reset_caches():
        """Clear all in-memory caches. Test/dev only."""
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
    @app.get("/download/{filename}")
    def download_file(filename: str):
        if not filename.endswith(".apk"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        path = os.path.join(_DOWNLOAD_DIR, filename)
        if not os.path.realpath(path).startswith(
            os.path.realpath(_DOWNLOAD_DIR) + os.sep
        ):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        if os.path.isfile(path):
            return FileResponse(
                path,
                media_type="application/vnd.android.package-archive",
                filename=filename,
            )
        return JSONResponse(status_code=404, content={"detail": "not found"})

    # WeChat domain verification — serves any file placed in static/wechat/
    # WeChat requires: GET https://yourdomain.com/<hash>.txt  → 200 OK, plain text content
    @app.get("/{filename}.txt")
    def wechat_verify(filename: str):
        path = os.path.join(_WECHAT_STATIC_DIR, f"{filename}.txt")
        # Prevent path traversal — resolved path must stay inside the static dir.
        if not os.path.realpath(path).startswith(
            os.path.realpath(_WECHAT_STATIC_DIR) + os.sep
        ):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        if os.path.isfile(path):
            return FileResponse(path, media_type="text/plain")
        return JSONResponse(status_code=404, content={"detail": "not found"})

    @app.get("/healthz")
    async def healthz() -> Response:
        payload = await _health_snapshot(scheduler_fn, bg_worker_tasks_fn, startup_ready_fn)
        status_code = 200 if payload["status"] == "ok" else 503
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/readyz")
    async def readyz() -> Response:
        if not startup_ready_fn():
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        payload = await _health_snapshot(scheduler_fn, bg_worker_tasks_fn, startup_ready_fn)
        if payload["status"] != "ok":
            return JSONResponse(
                status_code=503, content={"status": "not_ready", **payload}
            )
        return JSONResponse(status_code=200, content={"status": "ready"})


def _check_bg_workers(bg_worker_tasks) -> tuple[bool, list[str]]:
    """Return (all_alive, list_of_dead_worker_names)."""
    dead: list[str] = []
    for task in bg_worker_tasks:
        if task.done():
            dead.append(task.get_name())
    return len(dead) == 0, dead


async def _health_snapshot(scheduler_fn, bg_worker_tasks_fn, startup_ready_fn) -> dict:
    import logging
    db_ok = True
    db_error: Optional[str] = None
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)
        logging.getLogger("health").warning(
            "[Healthz] database check failed: %s", db_error
        )

    scheduler_ok = bool(scheduler_fn().running)
    workers_ok, dead_workers = _check_bg_workers(bg_worker_tasks_fn())

    all_ok = db_ok and scheduler_ok and workers_ok
    status = "ok" if all_ok else "degraded"
    payload: Dict[str, Any] = {
        "status": status,
        "checks": {
            "database": {"ok": db_ok},
            "scheduler": {"ok": scheduler_ok},
            "workers": {"ok": workers_ok},
            "startup": {"ok": bool(startup_ready_fn())},
        },
    }
    if db_error:
        # Don't leak raw exception details (may contain connection strings).
        payload["checks"]["database"]["error"] = "database_unavailable"
    if dead_workers:
        payload["checks"]["workers"]["dead"] = dead_workers
    return payload
