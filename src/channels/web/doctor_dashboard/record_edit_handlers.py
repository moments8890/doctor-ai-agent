"""
Record edit routes: update, delete, and admin correction operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.crud.records import delete_record
from db.engine import get_db
from db.models import MedicalRecordDB
# FieldEntryDB import removed 2026-04-26 (alembic 6a5d3c2e1f47) —
# per-field provenance now lives on MedicalRecordDB.carry_forward_meta
# and .fields_updated_this_visit; see get_record_entries below.
from infra.observability.audit import audit
from utils.log import safe_create_task
from channels.web.doctor_dashboard.deps import _resolve_ui_doctor_id, _require_ui_admin_access
from channels.web.doctor_dashboard.filters import _fmt_ts, _parse_tags

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Models ────────────────────────────────────────────────────────────────────

class RecordUpdate(BaseModel):
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    record_type: Optional[str] = None
    # 2026-04-26: ReviewPage completed-record edit mode lets the doctor tweak
    # 诊断 / 检查建议 / 治疗方向 in place after AI review without going back
    # through the AI suggestion flow. The handler already copies all structured
    # columns to a versioned row and applies updates via setattr; only the
    # schema needs to allow these fields. 检查建议 lands on `auxiliary_exam`
    # as the canonical column once the doctor has edited it (display falls
    # back to the joined-from-suggestions string when the column is empty).
    diagnosis: Optional[str] = None
    auxiliary_exam: Optional[str] = None
    treatment_plan: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.patch("/api/manage/records/{record_id}", include_in_schema=True)
async def update_record(
    record_id: int,
    body: RecordUpdate,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    rec = (await db.execute(
        select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == resolved_doctor_id,
        ).limit(1)
    )).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=404, detail="Record not found")
    # Append-only versioning: create new row with version_of pointing to original
    updates = body.model_dump(exclude_unset=True)
    if "tags" in updates and isinstance(updates["tags"], list):
        import json as _json
        updates["tags"] = _json.dumps(updates["tags"], ensure_ascii=False)

    # Copy all fields from original, apply updates
    new_rec = MedicalRecordDB(
        doctor_id=rec.doctor_id,
        patient_id=rec.patient_id,
        version_of=rec.id,
        record_type=rec.record_type,
        status=rec.status,
        content=rec.content,
        tags=rec.tags,
        department=rec.department,
        chief_complaint=rec.chief_complaint,
        present_illness=rec.present_illness,
        past_history=rec.past_history,
        allergy_history=rec.allergy_history,
        personal_history=rec.personal_history,
        marital_reproductive=rec.marital_reproductive,
        family_history=rec.family_history,
        physical_exam=rec.physical_exam,
        specialist_exam=rec.specialist_exam,
        auxiliary_exam=rec.auxiliary_exam,
        diagnosis=rec.diagnosis,
        # ai_diagnosis / doctor_decisions dropped — now in ai_suggestions table
        treatment_plan=rec.treatment_plan,
        orders_followup=rec.orders_followup,
        suggested_tasks=rec.suggested_tasks,
        final_diagnosis=rec.final_diagnosis,
        treatment_outcome=rec.treatment_outcome,
        key_symptoms=rec.key_symptoms,
    )
    # Apply the updates to the new record
    for field, value in updates.items():
        setattr(new_rec, field, value)
    db.add(new_rec)
    await db.commit()
    await db.refresh(new_rec)
    # Update last_activity_at for the patient
    if new_rec.patient_id:
        try:
            from db.crud.patient import touch_patient_activity
            await touch_patient_activity(db, new_rec.patient_id)
        except Exception:
            pass
    rec = new_rec
    return {
        "id": rec.id,
        "patient_id": rec.patient_id,
        "doctor_id": rec.doctor_id,
        "record_type": rec.record_type or "visit",
        "content": rec.content,
        "tags": _parse_tags(rec.tags),
        "version_of": rec.version_of,
        "diagnosis": rec.diagnosis,
        "auxiliary_exam": rec.auxiliary_exam,
        "treatment_plan": rec.treatment_plan,
        "created_at": _fmt_ts(rec.created_at),
        "updated_at": _fmt_ts(rec.updated_at),
    }


@router.delete("/api/manage/records/{record_id}", include_in_schema=True)
async def delete_record_endpoint(
    record_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    deleted = await delete_record(db, resolved_doctor_id, record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")
    safe_create_task(audit(resolved_doctor_id, "DELETE", "record", str(record_id)))
    return {"ok": True, "record_id": record_id}


@router.patch("/api/admin/records/{record_id}")
async def admin_update_record(
    record_id: int,
    body: RecordUpdate,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    db: AsyncSession = Depends(get_db),
):
    _require_ui_admin_access(x_admin_token)
    _ADMIN_RECORD_ALLOWED_FIELDS = {"content", "tags", "record_type"}
    rec = (await db.execute(
        select(MedicalRecordDB).where(MedicalRecordDB.id == record_id).limit(1)
    )).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=404, detail="Record not found")
    updates = body.model_dump(exclude_unset=True)
    disallowed = set(updates.keys()) - _ADMIN_RECORD_ALLOWED_FIELDS
    if disallowed:
        raise HTTPException(status_code=422, detail=f"Cannot update fields: {sorted(disallowed)}")
    if "tags" in updates and isinstance(updates["tags"], list):
        import json as _json
        updates["tags"] = _json.dumps(updates["tags"], ensure_ascii=False)
    # MedicalRecordVersion table removed — no version snapshot.
    for field, value in updates.items():
        setattr(rec, field, value)
    rec.updated_at = datetime.now(timezone.utc)
    owner_doctor_id = rec.doctor_id
    await db.commit()
    await db.refresh(rec)
    safe_create_task(audit(
        owner_doctor_id, "ADMIN_UPDATE", resource_type="record", resource_id=str(record_id),
    ))
    return {
        "id": rec.id,
        "patient_id": rec.patient_id,
        "doctor_id": rec.doctor_id,
        "record_type": rec.record_type or "visit",
        "content": rec.content,
        "tags": _parse_tags(rec.tags),
        "created_at": _fmt_ts(rec.created_at),
        "updated_at": _fmt_ts(rec.updated_at),
    }


# ── Field entries (append-only history) ──────────────────────────────────────

@router.get("/api/manage/records/{record_id}/entries", include_in_schema=True)
async def get_record_entries(
    record_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Return per-field provenance for a record (carry-forward + this-visit edits).

    Replaces the historical FieldEntryDB-based per-segment timeline. The
    intake redesign (alembic 6a5d3c2e1f47) consolidates record fields onto
    inline columns of medical_records; provenance lives in
    ``carry_forward_meta`` (which fields came from a prior record + when)
    and ``fields_updated_this_visit`` (which carry-forward fields the
    patient updated this visit). Frontend renders per-field badges from
    this shape.

    Response shape:
      {
        field_name: {
          "text": str,
          "carry_forward": {source_record_id, source_date, confirmed_by_patient} | None,
          "updated_this_visit": bool,
        },
        ...
      }

    The carry_forward / updated_this_visit fields are not currently
    rendered as per-field badges in the doctor UI (every confirmed value
    is approved data — provenance taxonomy added noise without actionable
    signal). They are kept on the wire and in medical_records.carry_forward_meta
    + .fields_updated_this_visit for future audit/analytics use.
    """
    resolved_doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)

    rec = (await db.execute(
        select(MedicalRecordDB).where(
            MedicalRecordDB.id == record_id,
            MedicalRecordDB.doctor_id == resolved_doctor_id,
        ).limit(1)
    )).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=404, detail="Record not found")

    cf_meta = rec.carry_forward_meta or {}
    updated = set(rec.fields_updated_this_visit or [])
    seven_fields = (
        "chief_complaint", "present_illness", "past_history", "allergy_history",
        "personal_history", "marital_reproductive", "family_history",
    )

    out: dict[str, dict] = {}
    for field in seven_fields:
        text = getattr(rec, field, None) or ""
        if not text:
            continue
        out[field] = {
            "text": text,
            "carry_forward": cf_meta.get(field),
            "updated_this_visit": field in updated,
        }
    return out
