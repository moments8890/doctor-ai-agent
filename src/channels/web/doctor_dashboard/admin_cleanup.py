"""
Admin cleanup API — detect and remove test/stale/orphaned data.

Endpoints:
  GET  /api/admin/cleanup/preview   — dry-run showing what would be cleaned
  POST /api/admin/cleanup/execute   — actually delete data
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from channels.web.doctor_dashboard.deps import (
    _require_ui_admin_access,
    require_admin_super,
)
from db.engine import get_db
from db.models import (
    AISuggestion,
    Doctor,
    DoctorChatLog,
    DoctorKnowledgeItem,
    DoctorTask,
    InterviewSessionDB,
    MedicalRecordDB,
    MessageDraft,
    Patient,
    PatientMessage,
)
from infra.observability.audit import audit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-cleanup"], include_in_schema=False)

# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

_STALE_DAYS = 7


def _test_doctor_filter():
    """SQLAlchemy filter for test/mock doctors."""
    return or_(
        func.lower(Doctor.doctor_id).contains("test"),
        func.lower(Doctor.doctor_id).contains("mock"),
        Doctor.doctor_id == "web_doctor",
        func.lower(Doctor.name).contains("test"),
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _find_test_doctors(db: AsyncSession) -> list[dict[str, Any]]:
    stmt = select(Doctor).where(_test_doctor_filter())
    rows = (await db.execute(stmt)).scalars().all()
    results = []
    for doc in rows:
        patient_count = (
            await db.execute(
                select(func.count()).where(Patient.doctor_id == doc.doctor_id)
            )
        ).scalar() or 0
        record_count = (
            await db.execute(
                select(func.count()).where(MedicalRecordDB.doctor_id == doc.doctor_id)
            )
        ).scalar() or 0

        reasons = []
        did = doc.doctor_id.lower()
        if "test" in did:
            reasons.append("doctor_id contains 'test'")
        if "mock" in did:
            reasons.append("doctor_id contains 'mock'")
        if doc.doctor_id == "web_doctor":
            reasons.append("doctor_id equals 'web_doctor'")
        if doc.name and "test" in doc.name.lower():
            reasons.append("name contains 'test'")

        results.append({
            "doctor_id": doc.doctor_id,
            "name": doc.name or "",
            "patient_count": patient_count,
            "record_count": record_count,
            "reason": "; ".join(reasons),
        })
    return results


async def _find_stale_patients(db: AsyncSession) -> list[dict[str, Any]]:
    cutoff = _now_utc() - timedelta(days=_STALE_DAYS)
    # Patients with no records AND no messages AND created > 7 days ago
    has_records = select(MedicalRecordDB.id).where(
        MedicalRecordDB.patient_id == Patient.id
    ).correlate(Patient).exists()
    has_messages = select(PatientMessage.id).where(
        PatientMessage.patient_id == Patient.id
    ).correlate(Patient).exists()

    stmt = select(Patient).where(
        and_(
            ~has_records,
            ~has_messages,
            Patient.created_at < cutoff,
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "doctor_id": p.doctor_id,
            "created_at": p.created_at.strftime("%Y-%m-%d") if p.created_at else "",
            "reason": "no records, no messages, created > 7 days ago",
        }
        for p in rows
    ]


async def _find_orphaned_records(db: AsyncSession) -> list[dict[str, Any]]:
    """Rows in child tables whose doctor_id is not in the doctors table."""
    doctor_ids_subq = select(Doctor.doctor_id)
    results: list[dict[str, Any]] = []

    tables = [
        ("medical_records", MedicalRecordDB),
        ("doctor_tasks", DoctorTask),
        ("ai_suggestions", AISuggestion),
        ("patient_messages", PatientMessage),
    ]
    for label, model in tables:
        stmt = select(model.id, model.doctor_id).where(
            ~model.doctor_id.in_(doctor_ids_subq)
        )
        rows = (await db.execute(stmt)).all()
        for row in rows:
            results.append({
                "id": row[0],
                "doctor_id": row[1],
                "table": label,
                "reason": "doctor_id not in doctors table",
            })
    return results


async def _find_duplicate_doctors(db: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(Doctor.name, func.count().label("cnt"))
        .where(Doctor.name.isnot(None))
        .group_by(Doctor.name)
        .having(func.count() > 1)
    )
    rows = (await db.execute(stmt)).all()
    results = []
    for name, cnt in rows:
        ids_stmt = select(Doctor.doctor_id).where(Doctor.name == name)
        ids = [r[0] for r in (await db.execute(ids_stmt)).all()]
        results.append({
            "name": name,
            "count": cnt,
            "doctor_ids": ids,
            "note": "manual review needed",
        })
    return results


# ---------------------------------------------------------------------------
# Cascade delete for a single doctor
# ---------------------------------------------------------------------------

# Order matters: delete from leaf tables first to avoid FK issues on DBs
# without deferred constraints.
_CASCADE_TABLES = [
    ("message_drafts", MessageDraft),       # → patient_messages.id
    ("ai_suggestions", AISuggestion),       # → medical_records.id
    ("patient_messages", PatientMessage),    # → patients.id, doctors.doctor_id
    ("doctor_chat_log", DoctorChatLog),      # → doctors.doctor_id
    ("interview_sessions", InterviewSessionDB),  # → doctors, patients
    ("doctor_tasks", DoctorTask),            # → doctors, patients, medical_records
    ("medical_records", MedicalRecordDB),    # → patients, doctors
    ("doctor_knowledge_items", DoctorKnowledgeItem),  # → doctors
    ("patients", Patient),                   # → doctors
]


async def _cascade_delete_doctor(
    db: AsyncSession, doctor_id: str
) -> dict[str, int]:
    """Delete a doctor and all related rows.  Returns per-table counts."""
    counts: dict[str, int] = {}
    for label, model in _CASCADE_TABLES:
        result = await db.execute(
            delete(model).where(model.doctor_id == doctor_id)
        )
        counts[label] = result.rowcount  # type: ignore[assignment]

    # Finally delete the doctor row itself
    result = await db.execute(
        delete(Doctor).where(Doctor.doctor_id == doctor_id)
    )
    counts["doctors"] = result.rowcount  # type: ignore[assignment]
    return counts


def _merge_counts(total: dict[str, int], delta: dict[str, int]) -> None:
    for k, v in delta.items():
        total[k] = total.get(k, 0) + v


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/api/admin/cleanup/preview")
async def cleanup_preview(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: AsyncSession = Depends(get_db),
):
    """Dry-run: show what would be cleaned up without deleting anything."""
    _require_ui_admin_access(x_admin_token)

    test_doctors = await _find_test_doctors(db)
    stale_patients = await _find_stale_patients(db)
    orphaned_records = await _find_orphaned_records(db)
    duplicate_doctors = await _find_duplicate_doctors(db)

    total_rows = (
        sum(d["patient_count"] + d["record_count"] + 1 for d in test_doctors)
        + len(stale_patients)
        + len(orphaned_records)
    )

    return {
        "test_doctors": test_doctors,
        "stale_patients": stale_patients,
        "orphaned_records": orphaned_records,
        "duplicate_doctors": duplicate_doctors,
        "summary": {
            "test_doctors": len(test_doctors),
            "stale_patients": len(stale_patients),
            "orphaned_records": len(orphaned_records),
            "duplicate_doctors": len(duplicate_doctors),
            "total_rows_to_delete": total_rows,
        },
    }


@router.post("/api/admin/cleanup/execute")
async def cleanup_execute(
    action: str = Query(..., description="test_doctors | stale_patients | orphaned_records | all"),
    doctor_id: Optional[str] = Query(default=None, description="Target a specific doctor"),
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_admin_super),
):
    """Delete data matching the specified action or target doctor.

    Super-only: viewer-role tokens get 403 (Task 4.1).
    """

    deleted: dict[str, int] = {}

    # --- targeted single-doctor delete ---
    if doctor_id:
        counts = await _cascade_delete_doctor(db, doctor_id)
        _merge_counts(deleted, counts)
        await db.commit()
        await audit(
            doctor_id="admin",
            action="cleanup.execute",
            resource_type="doctor",
            resource_id=doctor_id,
        )
        logger.info("admin cleanup: deleted doctor %s — %s", doctor_id, deleted)
        return {"deleted": deleted, "action": f"doctor:{doctor_id}"}

    # --- bulk actions ---
    if action in ("test_doctors", "all"):
        test_docs = await _find_test_doctors(db)
        for doc in test_docs:
            counts = await _cascade_delete_doctor(db, doc["doctor_id"])
            _merge_counts(deleted, counts)

    if action in ("stale_patients", "all"):
        stale = await _find_stale_patients(db)
        if stale:
            stale_ids = [p["id"] for p in stale]
            # Delete drafts, messages, tasks, records for these patients first
            for label, model, col in [
                ("message_drafts", MessageDraft, MessageDraft.patient_id),
                ("patient_messages", PatientMessage, PatientMessage.patient_id),
                ("doctor_tasks", DoctorTask, DoctorTask.patient_id),
                ("medical_records", MedicalRecordDB, MedicalRecordDB.patient_id),
            ]:
                result = await db.execute(delete(model).where(col.in_(stale_ids)))
                deleted[label] = deleted.get(label, 0) + result.rowcount
            # Then the patients themselves
            result = await db.execute(
                delete(Patient).where(Patient.id.in_(stale_ids))
            )
            deleted["patients"] = deleted.get("patients", 0) + result.rowcount

    if action in ("orphaned_records", "all"):
        doctor_ids_subq = select(Doctor.doctor_id)
        orphan_tables = [
            ("message_drafts", MessageDraft),
            ("ai_suggestions", AISuggestion),
            ("patient_messages", PatientMessage),
            ("doctor_tasks", DoctorTask),
            ("medical_records", MedicalRecordDB),
        ]
        for label, model in orphan_tables:
            result = await db.execute(
                delete(model).where(~model.doctor_id.in_(doctor_ids_subq))
            )
            deleted[label] = deleted.get(label, 0) + result.rowcount

    await db.commit()

    await audit(
        doctor_id="admin",
        action="cleanup.execute",
        resource_type="cleanup",
        resource_id=action,
    )
    logger.info("admin cleanup [%s]: %s", action, deleted)
    return {"deleted": deleted, "action": action}
