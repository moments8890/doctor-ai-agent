"""Case history endpoints — STUB.

CaseHistory table has been removed. These endpoints return 501/empty
to avoid breaking existing UI integrations.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/case-history")
async def list_cases_endpoint(**kwargs):
    return {"cases": []}


@router.get("/api/manage/case-history/{case_id}")
async def get_case_detail_endpoint(case_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="CaseHistory table removed")


@router.patch("/api/manage/case-history/{case_id}", include_in_schema=True)
async def enrich_case_endpoint(case_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="CaseHistory table removed")
