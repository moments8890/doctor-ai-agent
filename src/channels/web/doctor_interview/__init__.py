"""Doctor interview endpoints — structured clinical data entry."""
from channels.web.doctor_interview.routes import router  # noqa: F401

# Re-export shared types for backward compat
from channels.web.doctor_interview.shared import (  # noqa: F401
    DoctorInterviewResponse,
    InterviewConfirmResponse,
    FieldUpdateRequest,
    CarryForwardConfirmRequest,
    CarryForwardConfirmResponse,
    _build_clinical_text,
    _compute_progress,
)

# Re-export confirm endpoint for test runner
from channels.web.doctor_interview.confirm import interview_confirm_endpoint  # noqa: F401
