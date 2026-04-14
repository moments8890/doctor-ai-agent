"""APScheduler configuration: daily overdue digest, cleanup jobs, retention jobs."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from domain.tasks.task_crud import check_and_send_due_tasks


# ---------------------------------------------------------------------------
# Scheduled job functions
# ---------------------------------------------------------------------------

async def _cleanup_chat_log() -> None:
    """Daily job: hard-delete DoctorChatLog rows older than 365 days."""
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import cleanup_chat_log
        from db.engine import AsyncSessionLocal
        async with AsyncSessionLocal() as _session:
            deleted = await cleanup_chat_log(_session)
        _log.info("[DoctorChatLog] cleanup complete | deleted=%s", deleted)
    except Exception as _e:
        _log.warning("[DoctorChatLog] cleanup job FAILED: %s", _e)


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
    """Register daily overdue-task digest at 08:30 local time."""
    scheduler.add_job(check_and_send_due_tasks, "cron", hour=8, minute=30)
    startup_log.info("[Tasks] scheduler configured | mode=cron daily at 08:30")


def _schedule_retention_jobs(scheduler: AsyncIOScheduler, startup_log: logging.Logger) -> None:
    """Register data retention / compliance scheduled jobs (daily/monthly)."""
    scheduler.add_job(_cleanup_chat_log, "cron", hour=4, minute=30)
    startup_log.info("[DoctorChatLog] cleanup scheduler configured | daily at 04:30")

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
