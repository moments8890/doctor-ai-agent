"""APScheduler configuration: task notifications, cleanup jobs, retention jobs."""

import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.engine import AsyncSessionLocal
from domain.tasks.task_crud import check_and_send_due_tasks
from utils.log import safe_create_task


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

async def _expire_stale_pending_records() -> None:
    """Scheduler job: auto-save timed-out pending drafts instead of discarding them.

    For each stale draft: save to medical_records, then create a doctor_task
    notification so the doctor can see what was auto-saved in the tasks tab.
    """
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import get_stale_pending_records
        from domain.records.confirm_pending import save_pending_record
        from domain.tasks.task_crud import create_general_task
        from agent.pending import clear_pending_draft_id
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
                await clear_pending_draft_id(pending.doctor_id)
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
    """Daily job: hard-delete ChatArchive rows older than 365 days."""
    _log = logging.getLogger("scheduler")
    try:
        from db.crud import cleanup_chat_archive
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


def _schedule_cleanup_jobs(scheduler: AsyncIOScheduler, startup_log: logging.Logger) -> None:
    """Register draft expiry timer."""
    scheduler.add_job(_expire_stale_pending_records, "interval", minutes=5)
    startup_log.info("[PendingRecords] expiry scheduler configured | every_minutes=5")


def _schedule_retention_jobs(scheduler: AsyncIOScheduler, startup_log: logging.Logger) -> None:
    """Register data retention / compliance scheduled jobs (daily/monthly)."""
    scheduler.add_job(_purge_old_pending_data, "cron", hour=4, minute=0)
    startup_log.info("[Pending] purge scheduler configured | daily at 04:00")

    scheduler.add_job(_cleanup_chat_archive, "cron", hour=4, minute=30)
    startup_log.info("[ChatArchive] cleanup scheduler configured | daily at 04:30")

    scheduler.add_job(_audit_log_retention, "cron", day=1, hour=3, minute=0)
    startup_log.info("[AuditLog] retention scheduler configured | monthly day=1 at 03:00")

    scheduler.add_job(_record_version_retention, "cron", day=1, hour=3, minute=30)
    startup_log.info("[RecordVersions] retention scheduler configured | monthly day=1 at 03:30")

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
    _schedule_cleanup_jobs(scheduler, startup_log)
    _schedule_retention_jobs(scheduler, startup_log)
