from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DomainError(Exception):
    message: str
    status_code: int = 400
    error_code: str = "domain_error"
    context: Dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class PatientNotFoundError(DomainError):
    def __init__(self, message: str = "Patient not found", context: Optional[Dict[str, str]] = None):
        super().__init__(
            message=message,
            status_code=404,
            error_code="patient_not_found",
            context=context or {},
        )


class InvalidMedicalRecordError(DomainError):
    def __init__(self, message: str = "Invalid medical record", context: Optional[Dict[str, str]] = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="invalid_medical_record",
            context=context or {},
        )


class ExternalDependencyError(DomainError):
    def __init__(self, message: str = "External dependency error", context: Optional[Dict[str, str]] = None):
        super().__init__(
            message=message,
            status_code=503,
            error_code="external_dependency_error",
            context=context or {},
        )
