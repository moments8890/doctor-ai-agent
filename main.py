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
from utils.log import init_logging, safe_create_task
from utils.app_config import AppConfig, load_config_from_json, ollama_base_url_candidates

# Must run before any module reads os.environ.
# NOTE (architectural debt): several modules (llm_client, vision, etc.) snapshot
# env vars into module-level dicts at import time.  This works because main.py
# loads config/runtime.json here before importing routers, but alternate
# entrypoints or early imports can freeze the wrong provider configuration.
# TODO: migrate to lazy provider resolution via provider_registry.resolve().
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
from routers.patient_portal import router as patient_portal_router
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

async def _warmup_jieba(log: logging.Logger) -> None:
    """预加载 jieba 分词词典（首次导入时构建前缀词典）。"""
    import jieba
    jieba.initialize()
    log.info("jieba initialised")


async def _ping_ollama_candidate(
    candidate_url: str, model: str, api_key: str, timeout: float, max_attempts: int, log: logging.Logger
) -> bool:
    """尝试 ping 单个候选 URL；成功返回 True，连接失败返回 False，其他错误抛出。"""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=candidate_url, api_key=api_key, timeout=timeout, max_retries=0)
    for attempt in range(1, max_attempts + 1):
        try:
            await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=1,
            )
            return True
        except Exception as e:
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
    return False


def _apply_ollama_url_override(config: AppConfig, chosen_url: str, log: logging.Logger) -> None:
    """将选中的候选 URL 写入环境变量（当它与配置中的原始 URL 不同时）。"""
    if chosen_url != config.ollama_base_url:
        os.environ["OLLAMA_BASE_URL"] = chosen_url
        if os.environ.get("OLLAMA_VISION_BASE_URL", "").strip() == config.ollama_base_url:
            os.environ["OLLAMA_VISION_BASE_URL"] = chosen_url
        log.warning(
            f"Ollama startup fallback selected | original_base_url={config.ollama_base_url} "
            f"effective_base_url={chosen_url} model={config.ollama_model}"
        )
    else:
        log.info(
            f"Ollama startup connectivity check passed | "
            f"base_url={chosen_url} model={config.ollama_model}"
        )


async def _warmup_ollama(config: AppConfig, log: logging.Logger) -> None:
    """Ping Ollama 以将模型预加载进显存，并选取可用的 base_url。"""
    model = config.ollama_model
    max_attempts = 3
    warmup_timeout = _ollama_warmup_timeout_seconds()
    candidates = ollama_base_url_candidates(config.ollama_base_url)
    api_key = config.ollama_api_key or "ollama"
    chosen_url = None

    for candidate_url in candidates:
        if await _ping_ollama_candidate(candidate_url, model, api_key, warmup_timeout, max_attempts, log):
            chosen_url = candidate_url
            break

    if chosen_url:
        _apply_ollama_url_override(config, chosen_url, log)
    else:
        log.error(
            f"Ollama unavailable on startup | attempted_base_urls={candidates} "
            f"model={model}. Continuing without warmup."
        )


async def _warmup_lkeap(log: logging.Logger) -> None:
    """预建立 LKEAP TCP/TLS 连接，加速首次请求。"""
    lkeap_key = os.environ.get("TENCENT_LKEAP_API_KEY", "").strip()
    if not lkeap_key:
        return
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


async def _warmup(config: AppConfig):
    """依次执行各组件预热：jieba、Ollama、LKEAP。"""
    log = logging.getLogger("warmup")
    await _warmup_jieba(log)
    if config.routing_llm == "ollama" or config.structuring_llm == "ollama":
        await _warmup_ollama(config, log)
    if config.routing_llm == "tencent_lkeap" or config.structuring_llm == "tencent_lkeap":
        await _warmup_lkeap(log)


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
    raw = os.environ.get("CONVERSATION_TURN_RETENTION_DAYS", "1095")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1095


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
        from services.domain.intent_handlers import save_pending_record
        from services.notify.tasks import create_general_task
        from services.session import clear_pending_record_id
        async with AsyncSessionLocal() as _session:
            stale = await get_stale_pending_records(_session)
        if not stale:
            return
        saved = 0
        for pending in stale:
            try:
                _result = await save_pending_record(
                    pending.doctor_id, pending, force_confirm=True,
                )
                clear_pending_record_id(pending.doctor_id)
                patient_name = _result[0] if _result else None
                if patient_name:
                    safe_create_task(create_general_task(
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



async def _purge_old_pending_data() -> None:
    """Daily job: hard-delete expired/abandoned pending records and done messages older than 30 days."""
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import purge_old_pending_records, purge_old_pending_messages
        async with AsyncSessionLocal() as _session:
            deleted_records = await purge_old_pending_records(_session)
            deleted_messages = await purge_old_pending_messages(_session)
        _log.info(
            "[Pending] purge complete | deleted_records=%s deleted_messages=%s",
            deleted_records, deleted_messages,
        )
    except Exception as _e:
        _log.warning("[Pending] purge job FAILED: %s", _e)


async def _cleanup_chat_archive() -> None:
    """Daily job: hard-delete ChatArchive rows older than 90 days."""
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import cleanup_chat_archive
        async with AsyncSessionLocal() as _session:
            deleted = await cleanup_chat_archive(_session)
        _log.info("[ChatArchive] cleanup complete | deleted=%s", deleted)
    except Exception as _e:
        _log.warning("[ChatArchive] cleanup job FAILED: %s", _e)


async def _audit_log_retention() -> None:
    """Monthly job: delete audit log entries older than 7 years (2555 days)."""
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import archive_old_audit_logs
        async with AsyncSessionLocal() as _session:
            deleted = await archive_old_audit_logs(_session)
        _log.info("[AuditLog] retention purge complete | deleted=%s", deleted)
    except Exception as _e:
        _log.warning("[AuditLog] retention job FAILED: %s", _e)


async def _record_version_retention() -> None:
    """Monthly job: delete medical record versions older than 30 years (10950 days)."""
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import prune_record_versions
        async with AsyncSessionLocal() as _session:
            deleted = await prune_record_versions(_session)
        _log.info("[RecordVersions] retention purge complete | deleted=%s", deleted)
    except Exception as _e:
        _log.warning("[RecordVersions] retention job FAILED: %s", _e)


async def _redact_old_conversation_content() -> None:
    """Daily job: replace content of conversation turns older than 30 days with '[redacted]'."""
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import redact_old_conversation_content
        async with AsyncSessionLocal() as _session:
            updated = await redact_old_conversation_content(_session)
        if updated:
            _log.info("[Conversation] content redaction complete | updated=%s", updated)
    except Exception as _e:
        _log.warning("[Conversation] content redaction job FAILED: %s", _e)


def _schedule_task_notifications(startup_log: logging.Logger) -> None:
    """注册任务通知定时器（interval 或 cron 模式）。"""
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


def _schedule_cleanup_jobs(startup_log: logging.Logger) -> None:
    """注册对话清理、Session 缓存清理和草稿过期定时器。"""
    cleanup_hours = max(1, int(os.environ.get("CONVERSATION_CLEANUP_INTERVAL_HOURS", "6")))
    _scheduler.add_job(_cleanup_old_conversation_turns, "interval", hours=cleanup_hours)
    startup_log.info("[Conversation] cleanup scheduler configured | every_hours=%s", cleanup_hours)

    session_cleanup_minutes = _session_cache_cleanup_interval_minutes()
    _scheduler.add_job(_cleanup_inactive_session_cache, "interval", minutes=session_cleanup_minutes)
    startup_log.info("[Session] cache cleanup scheduler configured | every_minutes=%s", session_cleanup_minutes)

    _scheduler.add_job(_expire_stale_pending_records, "interval", minutes=5)
    startup_log.info("[PendingRecords] expiry scheduler configured | every_minutes=5")


def _schedule_retention_jobs(startup_log: logging.Logger) -> None:
    """注册数据保留/合规定时任务（每日/每月）。"""
    _scheduler.add_job(_purge_old_pending_data, "cron", hour=4, minute=0)
    startup_log.info("[Pending] purge scheduler configured | daily at 04:00")

    _scheduler.add_job(_cleanup_chat_archive, "cron", hour=4, minute=30)
    startup_log.info("[ChatArchive] cleanup scheduler configured | daily at 04:30")

    _scheduler.add_job(_audit_log_retention, "cron", day=1, hour=3, minute=0)
    startup_log.info("[AuditLog] retention scheduler configured | monthly day=1 at 03:00")

    _scheduler.add_job(_record_version_retention, "cron", day=1, hour=3, minute=30)
    startup_log.info("[RecordVersions] retention scheduler configured | monthly day=1 at 03:30")

    _scheduler.add_job(_redact_old_conversation_content, "cron", hour=5, minute=0)
    startup_log.info("[Conversation] content redaction scheduler configured | daily at 05:00")


def _configure_task_scheduler(startup_log: logging.Logger) -> None:
    """清除所有任务并重新注册全部定时器。"""
    _scheduler.remove_all_jobs()
    _schedule_task_notifications(startup_log)
    _schedule_cleanup_jobs(startup_log)
    _schedule_retention_jobs(startup_log)


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
        from services.auth import is_production as _is_prod_migration
        if _is_prod_migration():
            raise RuntimeError(
                f"Alembic migration failed in production — refusing to start "
                f"against a potentially inconsistent schema: {exc}"
            ) from exc
        log.warning("[DB] Alembic migration failed — continuing in dev mode: %s", exc)


async def _startup_db_and_warmup(startup_log: logging.Logger) -> None:
    """初始化数据库表、迁移、填充提示词并预热 LLM。"""
    startup_log.info("[Config] loaded environment\n%s", APP_CONFIG.to_pretty_log())
    await create_tables()
    await _run_alembic_migrations()
    _added_doctors = await backfill_doctors_registry()
    startup_log.info("[DB] doctors backfill completed | inserted=%s", _added_doctors)
    await seed_prompts()
    await _warmup(APP_CONFIG)


_bg_worker_tasks: list[asyncio.Task] = []


async def _startup_background_workers() -> None:
    """启动可观测性写入器和审计 drain worker 异步任务。"""
    from services.observability.observability import _disk_writer
    from services.observability.audit import _audit_drain_worker
    _bg_worker_tasks.append(asyncio.create_task(_disk_writer(), name="disk_writer"))
    _bg_worker_tasks.append(asyncio.create_task(_audit_drain_worker(), name="audit_drain"))


async def _startup_recovery(startup_log: logging.Logger) -> None:
    """清理过期 session、记录待发任务数量并重新入队崩溃遗留消息。"""
    await _cleanup_old_conversation_turns()
    await _cleanup_inactive_session_cache()
    try:
        async with AsyncSessionLocal() as _session:
            _pending = await get_due_tasks(_session, datetime.now(timezone.utc))
            startup_log.info(f"[Tasks] {len(_pending)} pending unnotified task(s) at startup")
    except Exception as _e:
        startup_log.warning(f"[Tasks] startup task count failed: {_e}")
    try:
        from routers.wechat import recover_stale_pending_messages
        _recovered = await recover_stale_pending_messages(older_than_seconds=60)
        if _recovered:
            startup_log.info("[Recovery] re-queued stale pending_message(s) | count=%s", _recovered)
    except Exception as _e:
        startup_log.warning("[Recovery] stale pending_message recovery FAILED: %s", _e)


def _enforce_production_guards() -> None:
    """生产环境安全检查：确保关键密钥已设置。"""
    from services.auth import is_production
    if not is_production():
        return
    if not os.environ.get("WECHAT_ID_HMAC_KEY", "").strip():
        raise RuntimeError(
            "WECHAT_ID_HMAC_KEY must be set in production to ensure "
            "WeChat identifiers are hashed at rest. Refusing to start."
        )
    if not os.environ.get("PATIENT_PORTAL_SECRET", "").strip():
        raise RuntimeError(
            "PATIENT_PORTAL_SECRET must be set in production to ensure "
            "patient portal tokens are signed with a real secret. "
            "Refusing to start."
        )
    if not os.environ.get("MINIPROGRAM_TOKEN_SECRET", "").strip() or \
            os.environ.get("MINIPROGRAM_TOKEN_SECRET", "").strip() == "dev-miniprogram-secret":
        raise RuntimeError(
            "MINIPROGRAM_TOKEN_SECRET must be set to a strong random "
            "value in production (not the dev default). Refusing to start."
        )
    if not os.environ.get("CORS_ALLOW_ORIGINS", "").strip():
        raise RuntimeError(
            "CORS_ALLOW_ORIGINS must be set in production. Refusing to start."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _startup_ready
    _startup_log = logging.getLogger("startup")
    # Production guards FIRST — before any DB/LLM/worker side effects.
    # A missing secret should abort immediately, not after tables are
    # created, prompts seeded, and workers started.
    _enforce_production_guards()
    await _startup_db_and_warmup(_startup_log)
    await _startup_background_workers()
    await _startup_recovery(_startup_log)
    _configure_task_scheduler(_startup_log)
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
    description="Phase 2 MVP — 患者管理 + 语音/文字录入 → 结构化病历生成",
    version="0.2.0",
    lifespan=lifespan,
)

_cors_origins_raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
if not _cors_origins:
    # Default to permissive origins in development only; production must
    # configure CORS_ALLOW_ORIGINS explicitly.
    from services.auth import is_production as _is_prod_cors
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
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token", "X-Trace-Id", "X-Patient-Token"],
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
            nonlocal _received
            message = await request.receive()
            body = message.get("body", b"")
            _received += len(body)
            if _received > _MAX_REQUEST_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Request body too large")
            return message

        request._receive = _counting_receive  # type: ignore[attr-defined]
    return await call_next(request)


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
app.include_router(mini_router)
app.include_router(ui_router)
app.include_router(neuro_router)
app.include_router(tasks_router)
app.include_router(voice_router)
app.include_router(export_router)
app.include_router(patient_portal_router)


@app.get("/")
def root():
    return {"status": "ok", "docs": "/docs"}


@app.get("/api/version")
def api_version():
    return {"version": 1, "app_version": "0.2.0"}


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
