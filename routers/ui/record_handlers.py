"""
病历列表处理器：_manage_records_for_doctor 的业务逻辑，供 UI 路由调用。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from db.crud import (
    get_all_records_for_doctor,
    get_records_for_patient,
    get_all_patients,
)
from sqlalchemy import func, select
from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB, Patient
from services.auth.rate_limit import enforce_doctor_rate_limit
from services.observability.audit import audit
from routers.ui._utils import (
    _fmt_ts,
    _parse_tags,
    _normalize_query_str,
    _normalize_date_yyyy_mm_dd,
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
        "encounter_type": record.encounter_type or "unknown",
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


async def _fetch_all_records(doctor_id: str, limit: int) -> list[dict]:
    """Fetch all records for a doctor, including joined patient name."""
    async with AsyncSessionLocal() as db:
        records = await get_all_records_for_doctor(db, doctor_id, limit=limit)

    return [
        _serialize_record_with_patient(r, r.patient.name if r.patient else None)
        for r in records
    ]


def _apply_name_filter(items: list[dict], patient_name: Optional[str]) -> list[dict]:
    if not patient_name:
        return items
    needle = patient_name.strip().lower()
    return [
        item for item in items
        if item.get("patient_name") and needle in str(item["patient_name"]).lower()
    ]


def _apply_date_filters(
    items: list[dict], date_from: Optional[str], date_to: Optional[str],
) -> list[dict]:
    if date_from:
        items = [i for i in items if i.get("created_at") and str(i["created_at"])[:10] >= date_from]
    if date_to:
        items = [i for i in items if i.get("created_at") and str(i["created_at"])[:10] <= date_to]
    return items


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


async def manage_patients_for_doctor(
    doctor_id: str,
    *,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """患者列表：按医生 ID 查询患者，支持分类过滤和分页。"""
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_patients")
    category = _normalize_query_str(category)
    asyncio.create_task(audit(doctor_id, "READ", "patient", "list"))
    async with AsyncSessionLocal() as db:
        patients, count_map = await _fetch_patients_with_record_counts(db, doctor_id)
    items = [_serialize_patient_item(p, count_map) for p in patients]
    if category is not None:
        items = [item for item in items if item["primary_category"] == category]
    total = len(items)
    return {"doctor_id": doctor_id, "items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}


async def manage_patients_grouped_for_doctor(doctor_id: str) -> dict:
    """患者分类列表：按分类分组返回全部患者。"""
    enforce_doctor_rate_limit(doctor_id, scope="ui.manage_patients_grouped")
    async with AsyncSessionLocal() as db:
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
    asyncio.create_task(audit(doctor_id, "READ", "record", _audit_resource_id))

    if patient_id is not None:
        items, _ = await _fetch_records_for_patient(doctor_id, patient_id, limit)
        patient_name = None  # name filter not applicable when filtering by id
    else:
        items = await _fetch_all_records(doctor_id, limit)
        items = _apply_name_filter(items, patient_name)

    items = _apply_date_filters(items, date_from, date_to)
    total = len(items)
    return {
        "doctor_id": doctor_id,
        "items": items[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
