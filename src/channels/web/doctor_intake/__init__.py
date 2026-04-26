"""Doctor intake endpoints — structured clinical data entry."""
from channels.web.doctor_intake.routes import router  # noqa: F401

# Re-export shared types for backward compat
from channels.web.doctor_intake.shared import (  # noqa: F401
    DoctorIntakeResponse,
    IntakeConfirmResponse,
    FieldUpdateRequest,
    CarryForwardConfirmRequest,
    CarryForwardConfirmResponse,
    _build_clinical_text,
    _compute_progress,
)

# Re-export confirm endpoint for test runner
from channels.web.doctor_intake.confirm import intake_confirm_endpoint  # noqa: F401
