"""Read engine: SELECT-only data fetching (ADR 0012 §5b).

Module-level constraint: no imports from pending_*, no write helpers.
This provides a hard boundary that prevents read handlers from
accidentally creating durable state.
"""
from __future__ import annotations

from typing import Any, Optional

from services.runtime.types import ActionType, ReadResult, ResolvedAction
from utils.log import log


async def read(action: ResolvedAction, doctor_id: str) -> ReadResult:
    """Fetch data for a read action. Never creates durable writes."""
    if action.action_type == ActionType.query_records:
        return await _query_records(action, doctor_id)
    elif action.action_type == ActionType.list_patients:
        return await _list_patients(doctor_id)
    elif action.action_type == ActionType.list_tasks:
        return await _list_tasks(action, doctor_id)
    else:
        log(f"read_engine called with non-read action: {action.action_type}", level="error")
        return ReadResult(status="error", error_key="execute_error")


async def _query_records(action: ResolvedAction, doctor_id: str) -> ReadResult:
    """Fetch medical records for a patient."""
    from db.engine import AsyncSessionLocal
    from db.repositories.records import RecordRepository

    # Get limit from args
    limit = 5
    if action.args and hasattr(action.args, "limit") and action.args.limit:
        limit = min(action.args.limit, 10)

    try:
        async with AsyncSessionLocal() as session:
            repo = RecordRepository(session)
            records = await repo.list_for_patient(
                doctor_id=doctor_id,
                patient_id=action.patient_id,
                limit=limit,
            )
            # Count using same patient_id filter for consistency
            from sqlalchemy import func, select
            from db.models import MedicalRecordDB
            count_result = await session.execute(
                select(func.count(MedicalRecordDB.id)).where(
                    MedicalRecordDB.doctor_id == doctor_id,
                    MedicalRecordDB.patient_id == action.patient_id,
                )
            )
            total_count = count_result.scalar() or 0

            if not records:
                return ReadResult(
                    status="empty",
                    data=[],
                    total_count=0,
                    truncated=False,
                    message_key="no_records",
                )

            # Serialize records for compose
            data = []
            for r in records:
                data.append({
                    "id": r.id,
                    "content": r.content,
                    "record_type": r.record_type,
                    "tags": r.tags,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })

            return ReadResult(
                status="ok",
                data=data,
                total_count=total_count,
                truncated=total_count > len(data),
            )
    except Exception as e:
        log(f"query_records failed: {e}", level="error")
        return ReadResult(status="error", error_key="execute_error")


async def _list_patients(doctor_id: str) -> ReadResult:
    """Fetch doctor's patient panel, recency-ordered."""
    from db.engine import AsyncSessionLocal
    from db.repositories.patients import PatientRepository

    try:
        async with AsyncSessionLocal() as session:
            repo = PatientRepository(session)
            patients = await repo.list_for_doctor(
                doctor_id=doctor_id,
                limit=20,
            )

            if not patients:
                return ReadResult(
                    status="empty",
                    data=[],
                    total_count=0,
                    truncated=False,
                    message_key="no_patients",
                )

            data = []
            for p in patients:
                data.append({
                    "id": p.id,
                    "name": p.name,
                    "gender": p.gender,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                })

            return ReadResult(
                status="ok",
                data=data,
                total_count=len(data),
                truncated=False,  # pagination deferred
            )
    except Exception as e:
        log(f"list_patients failed: {e}", level="error")
        return ReadResult(status="error", error_key="execute_error")


async def _list_tasks(action: ResolvedAction, doctor_id: str) -> ReadResult:
    """Fetch doctor's pending tasks."""
    from db.engine import AsyncSessionLocal
    from db.repositories.tasks import TaskRepository

    status_filter = None
    if action.args and hasattr(action.args, "status") and action.args.status:
        status_filter = action.args.status

    try:
        async with AsyncSessionLocal() as session:
            repo = TaskRepository(session)
            tasks = await repo.list_for_doctor(
                doctor_id=doctor_id,
                status=status_filter or "pending",
                limit=20,
            )

            if not tasks:
                return ReadResult(
                    status="empty",
                    data=[],
                    total_count=0,
                    truncated=False,
                    message_key="no_tasks",
                )

            data = []
            for t in tasks:
                data.append({
                    "id": t.id,
                    "task_type": t.task_type,
                    "title": t.title,
                    "content": t.content,
                    "status": t.status,
                    "patient_id": t.patient_id,
                    "due_at": t.due_at.isoformat() if t.due_at else None,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                })

            return ReadResult(
                status="ok",
                data=data,
                total_count=len(data),
                truncated=False,
            )
    except Exception as e:
        log(f"list_tasks failed: {e}", level="error")
        return ReadResult(status="error", error_key="execute_error")
