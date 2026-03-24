"""Diagnosis endpoints — STUB.

DiagnosisResult table has been removed. These endpoints return 501
to avoid breaking existing UI integrations.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/api/manage/diagnosis/{record_id}", include_in_schema=True)
async def get_diagnosis_endpoint(record_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="DiagnosisResult table removed")


@router.patch("/api/manage/diagnosis/{diagnosis_id}/decide", include_in_schema=True)
async def decide_item_endpoint(diagnosis_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="DiagnosisResult table removed")


@router.post("/api/manage/diagnosis/{diagnosis_id}/confirm", include_in_schema=True)
async def confirm_diagnosis_endpoint(diagnosis_id: int, **kwargs):
    raise HTTPException(status_code=501, detail="DiagnosisResult table removed")
