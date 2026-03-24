"""
Label / category CRUD routes — STUB.

PatientLabel table has been removed. These endpoints return empty/501
to avoid breaking existing UI integrations.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/labels", include_in_schema=True)
async def list_labels(**kwargs):
    return {"items": []}


@router.post("/api/manage/labels", include_in_schema=True)
async def create_label_endpoint(**kwargs):
    raise HTTPException(status_code=501, detail="PatientLabel table removed")


@router.patch("/api/manage/labels/{label_id}", include_in_schema=True)
async def update_label_endpoint(label_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="PatientLabel table removed")


@router.delete("/api/manage/labels/{label_id}", include_in_schema=True)
async def delete_label_endpoint(label_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="PatientLabel table removed")
