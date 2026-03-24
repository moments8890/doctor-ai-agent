"""Review queue endpoints — STUB.

ReviewQueue, DiagnosisResult, and CaseHistory tables have been removed.
These endpoints return 501 to avoid breaking existing UI integrations.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/review-queue", include_in_schema=True)
async def list_review_queue(**kwargs):
    return {"items": [], "count": 0}


@router.get("/api/manage/review-queue/{queue_id}", include_in_schema=True)
async def get_review_detail_endpoint(queue_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="ReviewQueue table removed")


@router.post("/api/manage/review-queue/{queue_id}/confirm", include_in_schema=True)
async def confirm_review_endpoint(queue_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="ReviewQueue table removed")


@router.patch("/api/manage/review-queue/{queue_id}/record", include_in_schema=True)
async def update_review_field_endpoint(queue_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="ReviewQueue table removed")
