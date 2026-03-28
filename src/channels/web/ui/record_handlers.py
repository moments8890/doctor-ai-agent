"""
病历列表处理器：_manage_records_for_doctor 的业务逻辑，供 UI 路由调用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from utils.log import safe_create_task
from db.crud import (
    get_all_records_for_doctor,
    count_records_for_doctor,
    get_records_for_patient,
    get_all_patients,
)
from sqlalchemy import and_, case, func, or_, select
from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB, Patient, PatientMessage
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


_RECORD_KEYS = (
    "department", "chief_complaint", "present_illness", "past_history",
    "allergy_history", "personal_history", "marital_reproductive", "family_history",
    "physical_exam", "specialist_exam", "auxiliary_exam",
    "diagnosis", "treatment_plan", "orders_followup",
)


def _serialize_record_with_patient(record, patient_name: Optional[str]) -> dict:
    """Turn a MedicalRecordDB row into a JSON-serializable dict."""
    d = {
        "id": record.id,
        "patient_id": record.patient_id,
        "doctor_id": record.doctor_id,
        "patient_name": patient_name,
        "record_type": record.record_type or "visit",
        "content": record.content,
        "tags": _parse_tags(record.tags),
        "status": record.status or "completed",
        "created_at": _fmt_ts(record.created_at),
        "updated_at": _fmt_ts(record.updated_at),
    }
    # Include non-empty clinical record fields for structured display
    structured = {}
    for key in _RECORD_KEYS:
        val = getattr(record, key, None)
        if val:
            structured[key] = val
    if structured:
        d["structured"] = structured
    return d


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




def _serialize_patient_item(p, count_map: dict, triage_map: Optional[dict] = None) -> dict:
    """Turn a Patient ORM row into a JSON-serializable dict for patient list endpoints."""
    d = {
        "id": p.id, "name": p.name, "gender": p.gender,
        "year_of_birth": p.year_of_birth, "created_at": _fmt_ts(p.created_at),
        "last_activity_at": _fmt_ts(getattr(p, "last_activity_at", None)),
        "record_count": int(count_map.get(p.id, 0)),
    }
    if triage_map:
        d["latest_triage_category"] = triage_map.get(p.id)
    return d


async def _fetch_latest_triage_map(db, doctor_id: str, patient_ids: list) -> dict:
    """Return {patient_id: triage_category} for the most recent message per patient."""
    if not patient_ids:
        return {}
    # Window function to pick the latest triage_category per patient.
    # Works on both SQLite and MySQL.
    inner = (
        select(
            PatientMessage.patient_id,
            PatientMessage.triage_category,
            func.row_number().over(
                partition_by=PatientMessage.patient_id,
                order_by=PatientMessage.created_at.desc(),
            ).label("rn"),
        )
        .where(
            PatientMessage.doctor_id == doctor_id,
            PatientMessage.patient_id.in_(patient_ids),
            PatientMessage.triage_category.is_not(None),
        )
        .subquery()
    )
    rows = (
        await db.execute(
            select(inner.c.patient_id, inner.c.triage_category)
            .where(inner.c.rn == 1)
        )
    ).all()
    return {pid: cat for pid, cat in rows}


async def _fetch_patients_with_record_counts(db, doctor_id: str) -> tuple[list, dict, dict]:
    """Return (patients, count_map, triage_map) for a doctor's namespace."""
    patients = await get_all_patients(db, doctor_id)
    counts_result = await db.execute(
        select(MedicalRecordDB.patient_id, func.count(MedicalRecordDB.id))
        .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id.is_not(None))
        .group_by(MedicalRecordDB.patient_id)
    )
    count_map = {pid: count for pid, count in counts_result.all()}
    pids = [p.id for p in patients]
    triage_map = await _fetch_latest_triage_map(db, doctor_id, pids)
    return patients, count_map, triage_map


async def _fetch_patients_cursor_page(
    db,
    doctor_id: str,
    *,
    category: Optional[str] = None,
    cursor_pair: Optional[Tuple[datetime, int]] = None,
    limit: int = 50,
) -> Tuple[list, dict, dict]:
    """Fetch one page of patients using keyset pagination.

    Ordering is ``(sort_ts DESC, id DESC)`` where ``sort_ts`` is
    ``COALESCE(last_activity_at, created_at)`` — most recently active
    patients first, deterministic even when timestamps collide.

    When *cursor_pair* is ``(ts, id)`` the query returns only rows that
    come **after** that position in the sort order.

    Returns ``(patients_page, count_map, triage_map)`` where *patients_page*
    has at most *limit* rows.
    """
    sort_ts = func.coalesce(Patient.last_activity_at, Patient.created_at)
    stmt = (
        select(Patient)
        .where(Patient.doctor_id == doctor_id)
        .order_by(sort_ts.desc(), Patient.id.desc())
    )
    if cursor_pair is not None:
        cursor_ts, cursor_id = cursor_pair
        # Keyset condition: row comes after (cursor_ts, cursor_id) in
        # ``(sort_ts DESC, id DESC)`` order.
        stmt = stmt.where(
            or_(
                sort_ts < cursor_ts,
                and_(sort_ts == cursor_ts, Patient.id < cursor_id),
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

    triage_map = await _fetch_latest_triage_map(db, doctor_id, pids)
    return patients, count_map, triage_map


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
            patients, count_map, triage_map = await _fetch_patients_cursor_page(
                db, doctor_id, category=category, cursor_pair=cursor_pair, limit=limit,
            )
            items = [_serialize_patient_item(p, count_map, triage_map) for p in patients]

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
            patients, count_map, triage_map = await _fetch_patients_with_record_counts(db, doctor_id)

    items = [_serialize_patient_item(p, count_map, triage_map) for p in patients]
    total = len(items)
    return {"doctor_id": doctor_id, "items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}


async def manage_patients_grouped_for_doctor(doctor_id: str) -> dict:
    """患者列表（分类功能已移除，返回全部患者在单一分组中）。"""
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_patients_grouped")
    async with AsyncSessionLocal() as db:
        patients, count_map, triage_map = await _fetch_patients_with_record_counts(db, doctor_id)
    items = [_serialize_patient_item(p, count_map, triage_map) for p in patients]
    return {"doctor_id": doctor_id, "groups": [{"group": "all", "count": len(items), "items": items}]}


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
