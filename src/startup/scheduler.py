"""APScheduler configuration: task notifications, cleanup jobs, retention jobs."""

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from domain.tasks.task_crud import check_and_send_due_tasks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Scheduled job functions
# ---------------------------------------------------------------------------

async def _cleanup_chat_archive() -> None:
    """Daily job: hard-delete ChatArchive rows older than 365 days."""
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import cleanup_chat_archive
        from db.engine import AsyncSessionLocal
        async with AsyncSessionLocal() as _session:
            deleted = await cleanup_chat_archive(_session)
        _log.info("[ChatArchive] cleanup complete | deleted=%s", deleted)
    except Exception as _e:
        _log.warning("[ChatArchive] cleanup job FAILED: %s", _e)


async def _audit_log_retention() -> None:
    """Monthly job: delete audit log entries older than 7 years (2555 days).

    WARNING: this directly deletes rows without archival/export.  In production,
    configure external log shipping (e.g. to S3/object storage) before this job
    runs, or the compliance trail will be permanently lost.
    """
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import archive_old_audit_logs
        from db.engine import AsyncSessionLocal
        async with AsyncSessionLocal() as _session:
            deleted = await archive_old_audit_logs(_session)
        if deleted:
            _log.warning(
                "[AuditLog] DELETED %s audit rows older than 7 years -- "
                "ensure external archival is configured for compliance",
                deleted,
            )
        else:
            _log.info("[AuditLog] retention check complete | no rows to purge")
    except Exception as _e:
        _log.warning("[AuditLog] retention job FAILED: %s", _e)


async def _prune_turn_log() -> None:
    """Daily job: remove turn log entries older than TURN_LOG_TTL_DAYS."""
    _log = logging.getLogger("scheduler")
    try:
        from infra.observability.turn_log import prune_turn_log
        kept = prune_turn_log()
        _log.info("[TurnLog] prune complete | kept=%s lines", kept)
    except Exception as _e:
        _log.warning("[TurnLog] prune job FAILED: %s", _e)


# ---------------------------------------------------------------------------
# Scheduler registration helpers
# ---------------------------------------------------------------------------

def _schedule_task_notifications(scheduler: AsyncIOScheduler, startup_log: logging.Logger) -> None:
    """Register task notification timer (interval or cron mode)."""
    mode = _scheduler_mode()
    if mode == "cron":
        cron_expr = _scheduler_cron_expr()
        try:
            minute, hour, day, month, day_of_week = cron_expr.split()
            scheduler.add_job(
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
            scheduler.add_job(check_and_send_due_tasks, "interval", minutes=interval_minutes)
            startup_log.warning(
                "[Tasks] invalid TASK_SCHEDULER_CRON=%r, fallback to interval=%s min",
                cron_expr,
                interval_minutes,
            )
    else:
        interval_minutes = _scheduler_interval_minutes()
        scheduler.add_job(check_and_send_due_tasks, "interval", minutes=interval_minutes)
        startup_log.info("[Tasks] scheduler configured | mode=interval minutes=%s", interval_minutes)


def _schedule_retention_jobs(scheduler: AsyncIOScheduler, startup_log: logging.Logger) -> None:
    """Register data retention / compliance scheduled jobs (daily/monthly)."""
    scheduler.add_job(_cleanup_chat_archive, "cron", hour=4, minute=30)
    startup_log.info("[ChatArchive] cleanup scheduler configured | daily at 04:30")

    scheduler.add_job(_audit_log_retention, "cron", day=1, hour=3, minute=0)
    startup_log.info("[AuditLog] retention scheduler configured | monthly day=1 at 03:00")

    scheduler.add_job(_prune_turn_log, "cron", hour=5, minute=30)
    startup_log.info("[TurnLog] prune scheduler configured | daily at 05:30")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def create_scheduler() -> AsyncIOScheduler:
    """Create and return a new AsyncIOScheduler instance."""
    return AsyncIOScheduler()


def configure_scheduler(scheduler: AsyncIOScheduler, startup_log: logging.Logger) -> None:
    """Clear all jobs and re-register all scheduled timers."""
    scheduler.remove_all_jobs()
    _schedule_task_notifications(scheduler, startup_log)
    _schedule_retention_jobs(scheduler, startup_log)
