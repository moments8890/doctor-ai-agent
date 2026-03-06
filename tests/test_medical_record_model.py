from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.medical_record import MedicalRecord


def test_medical_record_chief_complaint_cannot_be_empty():
    with pytest.raises(ValidationError):
        MedicalRecord(chief_complaint="   ")


def test_medical_record_field_length_limits():
    with pytest.raises(ValidationError):
        MedicalRecord(
            chief_complaint="胸痛",
            history_of_present_illness="x" * 9000,
        )
