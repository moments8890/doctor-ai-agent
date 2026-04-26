"""Doctor interview endpoints — thin hub with router and re-exports."""
from __future__ import annotations

from fastapi import APIRouter

from .shared import (  # noqa: F401  (re-exported for backwards compat)
    DoctorInterviewResponse,
    InterviewConfirmResponse,
    FieldUpdateRequest,
    CarryForwardConfirmRequest,
    CarryForwardConfirmResponse,
)
from . import turn as _turn_mod
from . import confirm as _confirm_mod

router = APIRouter(prefix="/api/records/interview", tags=["doctor-interview"])

router.include_router(_turn_mod.router)
router.include_router(_confirm_mod.router)
