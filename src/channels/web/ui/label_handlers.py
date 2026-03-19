"""
Label / category CRUD routes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from db.crud import (
    create_label,
    get_labels_for_doctor,
    update_label,
    delete_label,
)
from db.engine import AsyncSessionLocal
from infra.auth.rate_limit import enforce_doctor_rate_limit
from infra.observability.audit import audit
from utils.log import safe_create_task
from channels.web.ui._utils import _fmt_ts, _resolve_ui_doctor_id

router = APIRouter(tags=["ui"], include_in_schema=False)


# ── Models ────────────────────────────────────────────────────────────────────

class LabelCreate(BaseModel):
    doctor_id: str
    name: str
    color: Optional[str] = None


class LabelUpdate(BaseModel):
    doctor_id: str
    name: Optional[str] = None
    color: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/manage/labels", include_in_schema=True)
async def list_labels(
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.list")
    async with AsyncSessionLocal() as db:
        labels = await get_labels_for_doctor(db, doctor_id)
    return {
        "items": [
            {"id": lbl.id, "name": lbl.name, "color": lbl.color, "created_at": _fmt_ts(lbl.created_at)}
            for lbl in labels
        ]
    }


@router.post("/api/manage/labels", include_in_schema=True)
async def create_label_endpoint(body: LabelCreate, authorization: str | None = Header(default=None)):
    doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.create")
    async with AsyncSessionLocal() as db:
        lbl = await create_label(db, doctor_id, body.name, body.color)
    safe_create_task(audit(doctor_id, "WRITE", "label", str(lbl.id)))
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color, "created_at": _fmt_ts(lbl.created_at)}


@router.patch("/api/manage/labels/{label_id}", include_in_schema=True)
async def update_label_endpoint(label_id: int, body: LabelUpdate, authorization: str | None = Header(default=None)):
    doctor_id = _resolve_ui_doctor_id(body.doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.update")
    async with AsyncSessionLocal() as db:
        lbl = await update_label(db, label_id, doctor_id, name=body.name, color=body.color)
    if lbl is None:
        raise HTTPException(status_code=404, detail="Label not found")
    safe_create_task(audit(doctor_id, "WRITE", "label", str(label_id)))
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color}


@router.delete("/api/manage/labels/{label_id}", include_in_schema=True)
async def delete_label_endpoint(
    label_id: int,
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    doctor_id = _resolve_ui_doctor_id(doctor_id, authorization)
    enforce_doctor_rate_limit(doctor_id, scope="ui.labels.delete")
    async with AsyncSessionLocal() as db:
        found = await delete_label(db, label_id, doctor_id)
    if not found:
        raise HTTPException(status_code=404, detail="Label not found")
    safe_create_task(audit(doctor_id, "DELETE", "label", str(label_id)))
    return {"ok": True}
