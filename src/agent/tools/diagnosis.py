"""Diagnosis tools and case context injection for doctor chat.

CaseHistory table has been removed. Case context building is now a no-op.
TODO: migrate to medical_records-based case matching.
"""
from __future__ import annotations


async def _build_case_context(doctor_id: str, chief_complaint: str) -> str:
    """No-op — CaseHistory table removed. Returns empty string."""
    return ""
