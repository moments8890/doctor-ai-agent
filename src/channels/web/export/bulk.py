"""
Bulk export endpoints: start, poll status, and download a ZIP of all patient records.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from .shared import _content_disposition
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id
from infra.observability.audit import audit
from services.export.bulk_export import (
    BulkExportTask,
    cleanup_expired_tasks,
    create_task as create_bulk_task,
    generate_bulk_export,
    get_task as get_bulk_task,
    has_generating_task,
    has_recent_task,
)
from utils.log import log, safe_create_task

bulk_router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _BulkDownloadCleanup:
    """Starlette BackgroundTask that resets the downloading flag after response."""

    def __init__(self, task: BulkExportTask):
        self._task = task

    async def __call__(self) -> None:
        self._task.downloading = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@bulk_router.post("/bulk")
async def start_bulk_export(
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Launch a background bulk export of all patients for this doctor.

    Returns 202 with ``{"task_id": "..."}`` on success.
    Returns 429 if another export is already in progress or a recent one exists.
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)

    # Housekeeping — evict expired tasks
    cleanup_expired_tasks()

    # Rate limit: one export per hour
    if has_recent_task(resolved_doctor_id):
        raise HTTPException(
            status_code=429,
            detail="最近已有导出任务，请稍后再试",
            headers={"Retry-After": "3600"},
        )

    # Concurrency: only one generating task at a time
    if has_generating_task(resolved_doctor_id):
        raise HTTPException(
            status_code=429,
            detail="另一个导出正在进行中",
        )

    task = create_bulk_task(resolved_doctor_id)

    # Run the synchronous generate_bulk_export in a thread executor
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, generate_bulk_export, resolved_doctor_id, task)

    safe_create_task(audit(resolved_doctor_id, "EXPORT", resource_type="bulk", resource_id=task.task_id))
    log(f"[BulkExport] started task={task.task_id} doctor={resolved_doctor_id}")

    return JSONResponse(
        status_code=202,
        content={"task_id": task.task_id},
    )


@bulk_router.get("/bulk/{task_id}")
async def get_bulk_export_status(
    task_id: str,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Poll the status of a bulk export task.

    Returns status, progress, and download_url (when ready).
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    task = get_bulk_task(task_id)

    if task is None or task.doctor_id != resolved_doctor_id:
        raise HTTPException(status_code=404, detail="Export task not found")

    result: dict = {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress,
    }

    if task.status == "ready":
        result["download_url"] = f"/api/export/bulk/{task.task_id}/download"
    elif task.status == "failed":
        result["error"] = task.error or "导出失败"

    return JSONResponse(content=result)


@bulk_router.get("/bulk/{task_id}/download")
async def download_bulk_export(
    task_id: str,
    doctor_id: str = Query(default="web_doctor"),
    authorization: Optional[str] = Header(default=None),
):
    """
    Download the completed bulk export ZIP file.

    Requires the task to be in ``ready`` status.
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    task = get_bulk_task(task_id)

    if task is None or task.doctor_id != resolved_doctor_id:
        raise HTTPException(status_code=404, detail="Export task not found")

    if task.status != "ready":
        raise HTTPException(status_code=400, detail="Export is not ready for download")

    if not task.file_path:
        raise HTTPException(status_code=500, detail="Export file missing")

    task.downloading = True

    # Build filename: 导出_YYYY-MM-DD.zip
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"\u5bfc\u51fa_{date_str}.zip"  # 导出_{date}.zip

    try:
        return FileResponse(
            path=task.file_path,
            media_type="application/zip",
            headers={"Content-Disposition": _content_disposition(filename)},
            background=_BulkDownloadCleanup(task),
        )
    except Exception:
        task.downloading = False
        raise
