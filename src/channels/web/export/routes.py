"""
病历导出路由：生成患者病历 PDF，供医生下载或通过微信发送。

This module is a thin hub.  Endpoint logic lives in:
  - export_patient.py  — single-patient PDF & outpatient-report endpoints
  - export_bulk.py     — bulk ZIP export endpoints
  - export_shared.py   — shared filename/hash utilities
"""
from __future__ import annotations

from fastapi import APIRouter

from .bulk import bulk_router
from .patient import patient_router

# Re-export shared helpers so existing importers keep working.
from .shared import (  # noqa: F401
    _content_disposition,
    _safe_pdf_filename,
    _sha256_hex,
)

router = APIRouter(prefix="/api/export", tags=["export"])
router.include_router(patient_router)
router.include_router(bulk_router)
