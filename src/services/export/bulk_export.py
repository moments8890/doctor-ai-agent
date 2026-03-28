"""
批量导出：为医生的所有患者生成 ZIP 压缩包，包含每位患者的病历 PDF 和汇总 CSV。

ZIP 结构:
    {患者名}_p{id}/病历_{患者名}.pdf
    患者汇总.csv

任务状态保存在内存 dict 中（_bulk_tasks），30 分钟后过期自动清理。
"""
from __future__ import annotations

import csv
import io
import os
import re
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from utils.log import log


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------

@dataclass
class BulkExportTask:
    task_id: str
    doctor_id: str
    status: str  # "generating" | "ready" | "failed"
    progress: str  # "N/M"
    file_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    downloading: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_bulk_tasks: Dict[str, BulkExportTask] = {}
_font_cache: Optional[bytes] = None

_EXPIRY_SECONDS = 30 * 60  # 30 minutes
_RATE_LIMIT_SECONDS = 60 * 60  # 1 hour

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9\u4e00-\u9fff_\-]")


def _sanitize_name(name: str) -> str:
    """Strip characters outside [a-zA-Z0-9\\u4e00-\\u9fff_-], replace with _."""
    sanitized = _SAFE_NAME_RE.sub("_", name or "")
    return sanitized.strip("_") or "unknown"


def _csv_safe(value: str) -> str:
    """Defend against CSV injection: prefix dangerous leading chars with '."""
    if value and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _age_from_yob(year_of_birth: Optional[int]) -> Optional[int]:
    if not year_of_birth:
        return None
    return datetime.now().year - int(year_of_birth)


# ---------------------------------------------------------------------------
# Core export function (runs in thread executor — all sync)
# ---------------------------------------------------------------------------

def generate_bulk_export(doctor_id: str, task: BulkExportTask) -> None:
    """Generate a ZIP with per-patient PDFs + summary CSV.

    This function is SYNCHRONOUS and designed to run inside a thread executor.
    It uses synchronous DB access via asyncio.run() for each query batch to
    avoid holding a single connection open for the entire export.
    """
    import asyncio

    from db.engine import AsyncSessionLocal
    from db.models import MedicalRecordDB, Patient
    from domain.records.pdf_export import generate_records_pdf

    try:
        from sqlalchemy import func, select
    except ImportError:
        from sqlalchemy import select  # type: ignore[assignment]
        func = None  # type: ignore[assignment]

    tmp_dir = None
    zip_path = None

    try:
        # ---------------------------------------------------------------
        # 1. Query all patients for this doctor
        # ---------------------------------------------------------------
        async def _fetch_patients():
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Patient)
                    .where(Patient.doctor_id == doctor_id)
                    .order_by(Patient.created_at.asc())
                )
                return list(result.scalars().all())

        patients = asyncio.run(_fetch_patients())
        total = len(patients)

        if total == 0:
            task.status = "failed"
            task.error = "没有患者数据可导出"
            return

        task.progress = f"0/{total}"

        # ---------------------------------------------------------------
        # 2. Create temp dir and ZIP file
        # ---------------------------------------------------------------
        tmp_dir = tempfile.mkdtemp(prefix="bulk_export_")
        zip_path = os.path.join(tmp_dir, f"export_{doctor_id}_{int(time.time())}.zip")

        # Summary CSV data rows
        csv_rows: list[list[str]] = []

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # -----------------------------------------------------------
            # 3. Per-patient: fetch records, generate PDF, write to ZIP
            # -----------------------------------------------------------
            for i, patient in enumerate(patients):
                patient_id = patient.id
                patient_name = patient.name or ""

                async def _fetch_records(pid=patient_id):
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(
                            select(MedicalRecordDB)
                            .where(
                                MedicalRecordDB.patient_id == pid,
                                MedicalRecordDB.doctor_id == doctor_id,
                            )
                            .order_by(MedicalRecordDB.created_at.asc())
                        )
                        return list(result.scalars().all())

                records = asyncio.run(_fetch_records())

                # Generate PDF
                pdf_bytes = generate_records_pdf(
                    records=records,
                    patient=patient,
                    patient_name=patient_name,
                )

                # Build ZIP entry path
                safe_name = _sanitize_name(patient_name)
                folder = f"{safe_name}_p{patient_id}"
                pdf_filename = f"\u75c5\u5386_{safe_name}.pdf"  # 病历_{name}.pdf
                zf.writestr(f"{folder}/{pdf_filename}", pdf_bytes)

                # Collect CSV row
                record_count = len(records)
                latest_date = ""
                if records:
                    dates = [r.created_at for r in records if getattr(r, "created_at", None)]
                    if dates:
                        latest_date = max(dates).strftime("%Y-%m-%d")

                age = _age_from_yob(getattr(patient, "year_of_birth", None))
                csv_rows.append([
                    _csv_safe(patient_name),
                    _csv_safe(getattr(patient, "gender", None) or ""),
                    _csv_safe(str(age) if age is not None else ""),
                    _csv_safe(getattr(patient, "phone", None) or ""),
                    str(record_count),
                    latest_date,
                    folder,
                ])

                task.progress = f"{i + 1}/{total}"

            # -----------------------------------------------------------
            # 4. Write summary CSV into ZIP
            # -----------------------------------------------------------
            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            writer.writerow([
                "\u59d3\u540d",       # 姓名
                "\u6027\u522b",       # 性别
                "\u5e74\u9f84",       # 年龄
                "\u624b\u673a\u53f7",  # 手机号
                "\u75c5\u5386\u6570",  # 病历数
                "\u6700\u8fd1\u5c31\u8bca\u65e5\u671f",  # 最近就诊日期
                "\u6587\u4ef6\u5939\u540d",  # 文件夹名
            ])
            for row in csv_rows:
                writer.writerow(row)

            # Write with BOM for Excel CJK compatibility
            csv_bytes = ("\ufeff" + csv_buffer.getvalue()).encode("utf-8-sig")
            zf.writestr("\u60a3\u8005\u6c47\u603b.csv", csv_bytes)  # 患者汇总.csv

        # ---------------------------------------------------------------
        # 5. Done
        # ---------------------------------------------------------------
        task.file_path = zip_path
        task.status = "ready"
        log(f"[BulkExport] completed for doctor={doctor_id} patients={total} zip={zip_path}")

    except Exception as exc:
        log(f"[BulkExport] failed for doctor={doctor_id}: {exc}")
        task.status = "failed"
        task.error = "\u5bfc\u51fa\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5"  # 导出失败，请稍后重试

        # Cleanup partial files
        if zip_path and os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                os.rmdir(tmp_dir)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

def cleanup_expired_tasks() -> None:
    """Remove tasks older than 30 minutes (unless currently downloading)."""
    now = time.time()
    expired = [
        tid for tid, t in _bulk_tasks.items()
        if (now - t.created_at > _EXPIRY_SECONDS) and not t.downloading
    ]
    for tid in expired:
        t = _bulk_tasks.pop(tid, None)
        if t and t.file_path and os.path.exists(t.file_path):
            try:
                os.remove(t.file_path)
                # Try to remove the parent temp dir too
                parent = os.path.dirname(t.file_path)
                if parent and os.path.isdir(parent):
                    os.rmdir(parent)
            except OSError:
                pass
    if expired:
        log(f"[BulkExport] cleaned up {len(expired)} expired task(s)")


def get_task(task_id: str) -> Optional[BulkExportTask]:
    """Look up a bulk export task by ID."""
    return _bulk_tasks.get(task_id)


def create_task(doctor_id: str) -> BulkExportTask:
    """Create and register a new BulkExportTask."""
    task = BulkExportTask(
        task_id=str(uuid.uuid4()),
        doctor_id=doctor_id,
        status="generating",
        progress="0/0",
    )
    _bulk_tasks[task.task_id] = task
    return task


def has_recent_task(doctor_id: str) -> bool:
    """True if this doctor has a task created less than 1 hour ago."""
    now = time.time()
    for t in _bulk_tasks.values():
        if t.doctor_id == doctor_id and (now - t.created_at < _RATE_LIMIT_SECONDS):
            return True
    return False


def has_generating_task(doctor_id: str) -> bool:
    """True if this doctor has a task currently generating."""
    for t in _bulk_tasks.values():
        if t.doctor_id == doctor_id and t.status == "generating":
            return True
    return False
