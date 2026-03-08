"""
FastAPI 应用入口：生命周期管理、APScheduler 定时任务和启动恢复逻辑。
"""

import logging
import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from utils.log import init_logging
from utils.app_config import AppConfig, load_config_from_json, ollama_base_url_candidates

# Must run before any module reads os.environ.
_config_source_path, _config_values = load_config_from_json()
for _key, _value in _config_values.items():
    os.environ[_key] = _value
APP_CONFIG = AppConfig.from_env(env=_config_values, env_source=str(_config_source_path))
init_logging()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy import text
from starlette.responses import Response

from routers.records import router as records_router
from routers.wechat import router as wechat_router
from routers.auth import router as auth_router
from routers.miniprogram import router as mini_router
from routers.ui import router as ui_router
from routers.neuro import router as neuro_router
from routers.tasks import router as tasks_router
from routers.voice import router as voice_router
from routers.export import router as export_router
from db.init_db import create_tables, seed_prompts, backfill_doctors_registry
from db.engine import engine, AsyncSessionLocal
from db.crud import get_due_tasks, purge_conversation_turns_before
from services.notify.tasks import check_and_send_due_tasks
from services.session import prune_inactive_sessions
from utils.runtime_config import register_runtime_apply_hook
from utils.errors import DomainError
from services.observability.observability import (
    add_trace,
    reset_current_span_id,
    reset_current_trace_id,
    set_current_span_id,
    set_current_trace_id,
)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

async def _warmup(config: AppConfig):
    # Warm up jieba (builds prefix dict on first import)
    import jieba
    jieba.initialize()
    log = logging.getLogger("warmup")
    log.info("jieba initialised")

    # Verify/warm up Ollama — ping the model so it's loaded into memory.
    if config.routing_llm == "ollama" or config.structuring_llm == "ollama":
        from openai import AsyncOpenAI

        model = config.ollama_model
        max_attempts = 3
        warmup_timeout = _ollama_warmup_timeout_seconds()
        candidates = ollama_base_url_candidates(config.ollama_base_url)
        chosen_url = None
        last_error = None

        for candidate_url in candidates:
            client = AsyncOpenAI(
                base_url=candidate_url,
                api_key=config.ollama_api_key or "ollama",
                timeout=warmup_timeout,
                max_retries=0,
            )
            for attempt in range(1, max_attempts + 1):
                try:
                    await client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=1,
                    )
                    chosen_url = candidate_url
                    break
                except Exception as e:
                    last_error = e
                    if _is_connectivity_error(e):
                        log.warning(
                            f"Ollama connectivity check failed | "
                            f"base_url={candidate_url} model={model} attempt={attempt}/{max_attempts} error={e}"
                        )
                    else:
                        raise RuntimeError(
                            f"Ollama startup warmup failed with non-connectivity error "
                            f"(base_url={candidate_url}, model={model}): {e}"
                        ) from e
                    if attempt < max_attempts:
                        await asyncio.sleep(_ollama_warmup_backoff_seconds(attempt))
            if chosen_url:
                break

        if chosen_url:
            if chosen_url != config.ollama_base_url:
                os.environ["OLLAMA_BASE_URL"] = chosen_url
                if os.environ.get("OLLAMA_VISION_BASE_URL", "").strip() == config.ollama_base_url:
                    os.environ["OLLAMA_VISION_BASE_URL"] = chosen_url
                log.warning(
                    f"Ollama startup fallback selected | original_base_url={config.ollama_base_url} "
                    f"effective_base_url={chosen_url} model={model}"
                )
            else:
                log.info(
                    f"Ollama startup connectivity check passed | "
                    f"base_url={chosen_url} model={model}"
                )
        else:
            # Keep startup alive; runtime calls can still fallback or fail with explicit errors.
            log.error(
                f"Ollama unavailable on startup | attempted_base_urls={candidates} "
                f"model={model} error={last_error}. Continuing without warmup."
            )

    # Warm up LKEAP connection — pre-establishes TCP/TLS so first request is fast
    if config.routing_llm == "tencent_lkeap" or config.structuring_llm == "tencent_lkeap":
        lkeap_key = os.environ.get("TENCENT_LKEAP_API_KEY", "").strip()
        if lkeap_key:
            try:
                from services.ai.agent import _get_client, _PROVIDERS
                lkeap_provider = _PROVIDERS.get("tencent_lkeap", {})
                if lkeap_provider:
                    lkeap_client = _get_client("tencent_lkeap", dict(lkeap_provider))
                    lkeap_model = os.environ.get("TENCENT_LKEAP_MODEL", lkeap_provider.get("model", "deepseek-v3-1"))
                    await lkeap_client.chat.completions.create(
                        model=lkeap_model,
                        messages=[{"role": "user", "content": "hi"}],
                        max_tokens=1,
                    )
                    log.info("[Warmup] LKEAP connection established")
            except Exception as e:
                log.warning("[Warmup] LKEAP warmup failed (non-fatal): %s", e)


def _ollama_warmup_timeout_seconds() -> float:
    raw = os.environ.get("OLLAMA_WARMUP_TIMEOUT_SECONDS", "10").strip()
    try:
        value = float(raw)
        return value if value > 0 else 10.0
    except ValueError:
        return 10.0


def _ollama_warmup_backoff_seconds(attempt: int) -> float:
    # attempt is 1-based; retries use 1s, 2s, 4s...
    return float(2 ** max(0, int(attempt) - 1))


def _is_connectivity_error(exc: Exception) -> bool:
    """True when warmup failure indicates endpoint connectivity issues."""
    try:
        from openai import APIConnectionError, APITimeoutError
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return True
    except Exception:
        pass
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


_scheduler = AsyncIOScheduler()
_startup_ready = False


def _scheduler_mode() -> str:
    mode = os.environ.get("TASK_SCHEDULER_MODE", "interval").strip().lower()
    return mode if mode in {"interval", "cron"} else "interval"


def _scheduler_interval_minutes() -> int:
    raw = os.environ.get("TASK_SCHEDULER_INTERVAL_MINUTES", "1")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def _scheduler_cron_expr() -> str:
    return os.environ.get("TASK_SCHEDULER_CRON", "*/1 * * * *").strip() or "*/1 * * * *"


def _conversation_turn_retention_days() -> int:
    raw = os.environ.get("CONVERSATION_TURN_RETENTION_DAYS", "7")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 7


def _session_cache_cleanup_interval_minutes() -> int:
    raw = os.environ.get("SESSION_CACHE_CLEANUP_INTERVAL_MINUTES", "10")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 10


def _session_cache_max_idle_seconds() -> int:
    raw = os.environ.get("SESSION_CACHE_MAX_IDLE_SECONDS", "3600")
    try:
        return max(60, int(raw))
    except (TypeError, ValueError):
        return 3600


async def _cleanup_old_conversation_turns() -> None:
    retention_days = _conversation_turn_retention_days()
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        async with AsyncSessionLocal() as db:
            deleted = await purge_conversation_turns_before(db, cutoff)
        logging.getLogger("tasks").info(
            "[Conversation] cleanup complete | retention_days=%s deleted=%s",
            retention_days,
            deleted,
        )
    except Exception as exc:
        logging.getLogger("tasks").warning("[Conversation] cleanup failed: %s", exc)


async def _cleanup_inactive_session_cache() -> None:
    try:
        summary = prune_inactive_sessions(max_idle_seconds=_session_cache_max_idle_seconds())
        logging.getLogger("tasks").info("[Session] cache cleanup complete | %s", summary)
    except Exception as exc:
        logging.getLogger("tasks").warning("[Session] cache cleanup failed: %s", exc)


async def _expire_stale_pending_records() -> None:
    """Scheduler job: auto-save timed-out pending drafts instead of discarding them.

    For each stale draft: save to medical_records, then create a doctor_task
    notification so the doctor can see what was auto-saved in the tasks tab.
    """
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import get_stale_pending_records
        from services.wechat.wechat_domain import save_pending_record
        from services.notify.tasks import create_general_task
        from services.session import clear_pending_record_id
        async with AsyncSessionLocal() as _session:
            stale = await get_stale_pending_records(_session)
        if not stale:
            return
        saved = 0
        for pending in stale:
            try:
                patient_name = await save_pending_record(pending.doctor_id, pending)
                clear_pending_record_id(pending.doctor_id)
                if patient_name:
                    asyncio.ensure_future(create_general_task(
                        pending.doctor_id,
                        title=f"病历已自动保存：【{patient_name}】",
                        patient_id=pending.patient_id,
                    ))
                    saved += 1
            except Exception as _e:
                _log.warning("[PendingRecords] auto-save FAILED id=%s: %s", pending.id, _e)
        if saved:
            _log.info("[PendingRecords] auto-saved stale drafts | count=%s", saved)
    except Exception as _e:
        _log.warning("[PendingRecords] auto-save job FAILED: %s", _e)


async def _expire_stale_pending_imports() -> None:
    try:
        from db.crud import expire_stale_pending_imports
        async with AsyncSessionLocal() as session:
            n = await expire_stale_pending_imports(session)
        if n:
            logging.getLogger("scheduler").info("[Scheduler] expired %s pending imports", n)
    except Exception as e:
        logging.getLogger("scheduler").warning("[Scheduler] expire_pending_imports FAILED: %s", e)


def _configure_task_scheduler(startup_log: logging.Logger) -> None:
    _scheduler.remove_all_jobs()
    mode = _scheduler_mode()
    if mode == "cron":
        cron_expr = _scheduler_cron_expr()
        try:
            minute, hour, day, month, day_of_week = cron_expr.split()
            _scheduler.add_job(
                check_and_send_due_tasks,
                "cron",
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
            )
            startup_log.info("[Tasks] scheduler configured | mode=cron expr=%s", cron_expr)
        except Exception:
            interval_minutes = _scheduler_interval_minutes()
            _scheduler.add_job(check_and_send_due_tasks, "interval", minutes=interval_minutes)
            startup_log.warning(
                "[Tasks] invalid TASK_SCHEDULER_CRON=%r, fallback to interval=%s min",
                cron_expr,
                interval_minutes,
            )
    else:
        interval_minutes = _scheduler_interval_minutes()
        _scheduler.add_job(check_and_send_due_tasks, "interval", minutes=interval_minutes)
        startup_log.info("[Tasks] scheduler configured | mode=interval minutes=%s", interval_minutes)

    cleanup_hours = max(1, int(os.environ.get("CONVERSATION_CLEANUP_INTERVAL_HOURS", "6")))
    _scheduler.add_job(_cleanup_old_conversation_turns, "interval", hours=cleanup_hours)
    startup_log.info("[Conversation] cleanup scheduler configured | every_hours=%s", cleanup_hours)

    session_cleanup_minutes = _session_cache_cleanup_interval_minutes()
    _scheduler.add_job(_cleanup_inactive_session_cache, "interval", minutes=session_cleanup_minutes)
    startup_log.info("[Session] cache cleanup scheduler configured | every_minutes=%s", session_cleanup_minutes)

    _scheduler.add_job(_expire_stale_pending_records, "interval", minutes=5)
    startup_log.info("[PendingRecords] expiry scheduler configured | every_minutes=5")

    _scheduler.add_job(
        _expire_stale_pending_imports,
        "interval",
        minutes=5,
        id="expire_pending_imports",
    )
    startup_log.info("[PendingImports] expiry scheduler configured | every_minutes=5")


async def _runtime_apply_hook(_config: dict) -> None:
    log = logging.getLogger("runtime-config")
    if _scheduler.running:
        _configure_task_scheduler(log)


register_runtime_apply_hook(_runtime_apply_hook)


async def _run_alembic_migrations() -> None:
    """Run pending Alembic migrations synchronously in a thread pool."""
    import asyncio
    import logging
    from alembic.config import Config
    from alembic import command

    log = logging.getLogger("startup")

    def _run_sync() -> None:
        cfg = Config("alembic.ini")
        cfg.set_main_option("script_location", "alembic")
        command.upgrade(cfg, "head")

    try:
        await asyncio.get_event_loop().run_in_executor(None, _run_sync)
        log.info("[DB] Alembic migrations applied (or already at head)")
    except Exception as exc:
        log.warning("[DB] Alembic migration failed — continuing anyway: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_ready
    _startup_log = logging.getLogger("startup")
    _startup_log.info("[Config] loaded environment\n%s", APP_CONFIG.to_pretty_log())
    await create_tables()
    await _run_alembic_migrations()
    _added_doctors = await backfill_doctors_registry()
    _startup_log.info("[DB] doctors backfill completed | inserted=%s", _added_doctors)
    await seed_prompts()
    await _warmup(APP_CONFIG)
    # Start async observability disk writer — eliminates blocking file I/O on every request
    from services.observability.observability import _disk_writer
    asyncio.create_task(_disk_writer())
    await _cleanup_old_conversation_turns()
    await _cleanup_inactive_session_cache()

    # Log pending unnotified tasks on startup
    try:
        async with AsyncSessionLocal() as _session:
            _pending = await get_due_tasks(_session, datetime.now(timezone.utc))
            _startup_log.info(f"[Tasks] {len(_pending)} pending unnotified task(s) at startup")
    except Exception as _e:
        _startup_log.warning(f"[Tasks] startup task count failed: {_e}")

    # Re-queue messages left unprocessed from previous crash
    try:
        from routers.wechat import recover_stale_pending_messages
        _recovered = await recover_stale_pending_messages(older_than_seconds=60)
        if _recovered:
            _startup_log.info("[Recovery] re-queued stale pending_message(s) | count=%s", _recovered)
    except Exception as _e:
        _startup_log.warning("[Recovery] stale pending_message recovery FAILED: %s", _e)

    _configure_task_scheduler(_startup_log)
    _scheduler.start()
    _startup_ready = True
    yield
    _startup_ready = False
    _scheduler.shutdown()


app = FastAPI(
    title="专科医师AI智能体",
    description="Phase 2 MVP — 患者管理 + 语音/文字录入 → 结构化病历生成",
    version="0.2.0",
    lifespan=lifespan,
)

_cors_origins_raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token", "X-Trace-Id"],
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
        return response
    finally:
        reset_current_span_id(span_token)
        reset_current_trace_id(trace_token)


app.include_router(records_router)
app.include_router(wechat_router)
app.include_router(auth_router)
app.include_router(mini_router)
app.include_router(ui_router)
app.include_router(neuro_router)
app.include_router(tasks_router)
app.include_router(voice_router)
app.include_router(export_router)


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}


# WeChat domain verification — serves any file placed in static/wechat/
# WeChat requires: GET https://yourdomain.com/<hash>.txt  → 200 OK, plain text content
_WECHAT_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "wechat")

@app.get("/{filename}.txt")
def wechat_verify(filename: str):
    path = os.path.join(_WECHAT_STATIC_DIR, f"{filename}.txt")
    if os.path.isfile(path):
        return FileResponse(path, media_type="text/plain")
    return JSONResponse(status_code=404, content={"detail": "not found"})


@app.get("/healthz")
async def healthz() -> dict:
    return await _health_snapshot()


@app.get("/readyz")
async def readyz() -> Response:
    if _startup_ready and _scheduler.running:
        return JSONResponse(status_code=200, content={"status": "ready"})
    return JSONResponse(status_code=503, content={"status": "not_ready"})


async def _health_snapshot() -> dict:
    db_ok = True
    db_error: Optional[str] = None
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    scheduler_ok = bool(_scheduler.running)
    status = "ok" if db_ok and scheduler_ok else "degraded"
    payload: Dict[str, Any] = {
        "status": status,
        "checks": {
            "database": {"ok": db_ok},
            "scheduler": {"ok": scheduler_ok, "running": bool(_scheduler.running)},
            "startup": {"ok": bool(_startup_ready), "ready": bool(_startup_ready)},
        },
    }
    if db_error:
        payload["checks"]["database"]["error"] = db_error
    return payload
