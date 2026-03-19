"""
病历列表处理器：_manage_records_for_doctor 的业务逻辑，供 UI 路由调用。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, Tuple

from utils.log import safe_create_task
from db.crud import (
    get_all_records_for_doctor,
    count_records_for_doctor,
    get_records_for_patient,
    get_all_patients,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload
from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB, Patient
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.audit import audit
from channels.web.ui._utils import (
    _fmt_ts,
    _parse_tags,
    _normalize_query_str,
    _normalize_date_yyyy_mm_dd,
    encode_cursor,
    decode_cursor,
)


def _serialize_record_with_patient(record, patient_name: Optional[str]) -> dict:
    """Turn a MedicalRecordDB row into a JSON-serializable dict."""
    return {
        "id": record.id,
        "patient_id": record.patient_id,
        "doctor_id": record.doctor_id,
        "patient_name": patient_name,
        "record_type": record.record_type or "visit",
        "content": record.content,
        "tags": _parse_tags(record.tags),
        "needs_review": bool(record.needs_review) if record.needs_review is not None else False,
        "created_at": _fmt_ts(record.created_at),
        "updated_at": _fmt_ts(record.updated_at),
    }


async def _fetch_records_for_patient(
    doctor_id: str, patient_id: int, limit: int,
) -> tuple[list[dict], Optional[str]]:
    """Fetch records scoped to a single patient; returns (items, resolved_name)."""
    async with AsyncSessionLocal() as db:
        records = await get_records_for_patient(db, doctor_id, patient_id, limit=limit)
        patients = await get_all_patients(db, doctor_id)

    patient_name: Optional[str] = None
    for p in patients:
        if p.id == patient_id:
            patient_name = p.name
            break

    items = [_serialize_record_with_patient(r, patient_name) for r in records]
    return items, patient_name


async def _fetch_filtered_records(
    doctor_id: str,
    *,
    patient_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Fetch records with filters applied at the DB level. Returns (items, total)."""
    async with AsyncSessionLocal() as db:
        records = await get_all_records_for_doctor(
            db, doctor_id, limit=limit, offset=offset,
            patient_name=patient_name, date_from=date_from, date_to=date_to,
        )
        total = await count_records_for_doctor(
            db, doctor_id,
            patient_name=patient_name, date_from=date_from, date_to=date_to,
        )
    items = [
        _serialize_record_with_patient(r, r.patient.name if r.patient else None)
        for r in records
    ]
    return items, total


CATEGORY_ORDER = ["high_risk", "active_followup", "stable", "new", "uncategorized"]


def _serialize_patient_item(p, count_map: dict) -> dict:
    """Turn a Patient ORM row into a JSON-serializable dict for patient list endpoints."""
    return {
        "id": p.id, "name": p.name, "gender": p.gender,
        "year_of_birth": p.year_of_birth, "created_at": _fmt_ts(p.created_at),
        "record_count": int(count_map.get(p.id, 0)),
        "primary_category": p.primary_category,
        "category_tags": _parse_tags(p.category_tags),
        "labels": [{"id": lbl.id, "name": lbl.name, "color": lbl.color} for lbl in (p.labels or [])],
    }


async def _fetch_patients_with_record_counts(db, doctor_id: str) -> tuple[list, dict]:
    """Return (patients, count_map) for a doctor's namespace."""
    patients = await get_all_patients(db, doctor_id)
    counts_result = await db.execute(
        select(MedicalRecordDB.patient_id, func.count(MedicalRecordDB.id))
        .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id.is_not(None))
        .group_by(MedicalRecordDB.patient_id)
    )
    count_map = {pid: count for pid, count in counts_result.all()}
    return patients, count_map


async def _fetch_patients_cursor_page(
    db,
    doctor_id: str,
    *,
    category: Optional[str] = None,
    cursor_pair: Optional[Tuple[datetime, int]] = None,
    limit: int = 50,
) -> Tuple[list, dict]:
    """Fetch one page of patients using keyset pagination.

    Ordering is ``(created_at DESC, id DESC)`` — deterministic even when
    ``created_at`` values collide.

    When *cursor_pair* is ``(ts, id)`` the query returns only rows that
    come **after** that position in the sort order.

    Returns ``(patients_page, count_map)`` where *patients_page* has at
    most *limit* rows.
    """
    stmt = (
        select(Patient)
        .where(Patient.doctor_id == doctor_id)
        .options(selectinload(Patient.labels))
        .order_by(Patient.created_at.desc(), Patient.id.desc())
    )
    if category is not None:
        stmt = stmt.where(Patient.primary_category == category)
    if cursor_pair is not None:
        cursor_ts, cursor_id = cursor_pair
        # Keyset condition: row comes after (cursor_ts, cursor_id) in
        # ``(created_at DESC, id DESC)`` order.
        stmt = stmt.where(
            or_(
                Patient.created_at < cursor_ts,
                and_(Patient.created_at == cursor_ts, Patient.id < cursor_id),
            )
        )
    stmt = stmt.limit(limit)

    patients = list((await db.execute(stmt)).scalars().all())

    # Record counts for the patient IDs in this page
    pids = [p.id for p in patients]
    if pids:
        counts_result = await db.execute(
            select(MedicalRecordDB.patient_id, func.count(MedicalRecordDB.id))
            .where(
                MedicalRecordDB.doctor_id == doctor_id,
                MedicalRecordDB.patient_id.in_(pids),
            )
            .group_by(MedicalRecordDB.patient_id)
        )
        count_map = {pid: cnt for pid, cnt in counts_result.all()}
    else:
        count_map = {}

    return patients, count_map


async def manage_patients_for_doctor(
    doctor_id: str,
    *,
    category: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """患者列表：按医生 ID 查询患者，支持分类过滤和游标/偏移分页。

    When *cursor* is provided, keyset (cursor-based) pagination is used
    and *offset* is ignored.  The response includes a ``next_cursor``
    field that the client should pass for the next page.

    When *cursor* is ``None`` and *offset* is 0, the first page is
    returned — fully backward-compatible with the old offset pagination.
    """
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_patients")
    category = _normalize_query_str(category)
    safe_create_task(audit(doctor_id, "READ", "patient", "list"))

    # Normalize cursor — could be None, empty string, or a real cursor token
    effective_cursor: Optional[str] = cursor if isinstance(cursor, str) and cursor else None
    cursor_pair = decode_cursor(effective_cursor)

    # Use cursor-mode when a cursor is explicitly provided, or when the
    # client requests the first page (offset == 0).  Legacy offset mode
    # is only entered when offset > 0 *without* a cursor.
    use_cursor_mode = effective_cursor is not None or offset == 0

    async with AsyncSessionLocal() as db:
        if use_cursor_mode:
            patients, count_map = await _fetch_patients_cursor_page(
                db, doctor_id, category=category, cursor_pair=cursor_pair, limit=limit,
            )
            items = [_serialize_patient_item(p, count_map) for p in patients]

            # Build next_cursor from the last item when there may be more rows
            next_cursor: Optional[str] = None
            if len(patients) == limit:
                last = patients[-1]
                next_cursor = encode_cursor(last.created_at, last.id)

            return {
                "doctor_id": doctor_id,
                "items": items,
                "limit": limit,
                "next_cursor": next_cursor,
            }
        else:
            # Legacy offset mode (offset > 0 without cursor)
            patients, count_map = await _fetch_patients_with_record_counts(db, doctor_id)

    # Filter by category first, then paginate the filtered list
    if category is not None:
        patients = [p for p in patients if (p.primary_category or "uncategorized") == category]
    items = [_serialize_patient_item(p, count_map) for p in patients]
    total = len(items)
    return {"doctor_id": doctor_id, "items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}


async def manage_patients_grouped_for_doctor(doctor_id: str) -> dict:
    """患者分类列表：按分类分组返回全部患者。

    Refreshes time-based categories inline before serialising so that
    stale categories (e.g. 'active_followup' that has drifted past its
    window) are corrected on read, not only on record-save.
    """
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_patients_grouped")
    async with AsyncSessionLocal() as db:
        # Refresh stale categories before reading
        from domain.patients.categorization import recompute_all_categories
        await recompute_all_categories(db, doctor_id=doctor_id)
        patients, count_map = await _fetch_patients_with_record_counts(db, doctor_id)
    all_items = [_serialize_patient_item(p, count_map) for p in patients]
    bucket: dict = {cat: [] for cat in CATEGORY_ORDER}
    for item in all_items:
        cat = item["primary_category"] or "uncategorized"
        if cat not in bucket:
            cat = "uncategorized"
        bucket[cat].append(item)
    groups = [{"group": cat, "count": len(bucket[cat]), "items": bucket[cat]} for cat in CATEGORY_ORDER]
    return {"doctor_id": doctor_id, "groups": groups}


async def manage_records_for_doctor(
    doctor_id: str,
    *,
    patient_id: Optional[int] = None,
    patient_name: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """查询病历列表：按患者或全量返回，支持姓名和日期过滤。"""
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_records")
    patient_name = _normalize_query_str(patient_name)
    date_from = _normalize_date_yyyy_mm_dd(date_from)
    date_to = _normalize_date_yyyy_mm_dd(date_to)

    _audit_resource_id = str(patient_id) if patient_id is not None else "list"
    safe_create_task(audit(doctor_id, "READ", "record", _audit_resource_id))

    if patient_id is not None:
        # Single-patient view — no name/date filters needed beyond patient_id
        items, _ = await _fetch_records_for_patient(doctor_id, patient_id, limit)
        total = len(items)
    else:
        # All-records view — push name and date filters into DB query
        items, total = await _fetch_filtered_records(
            doctor_id,
            patient_name=patient_name,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

    return {
        "doctor_id": doctor_id,
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
