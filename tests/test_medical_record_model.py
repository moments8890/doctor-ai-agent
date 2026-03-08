from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.medical_record import MedicalRecord


def test_medical_record_content_cannot_be_empty():
    with pytest.raises(ValidationError):
        MedicalRecord(content="   ")


def test_medical_record_content_required():
    with pytest.raises(ValidationError):
        MedicalRecord()


def test_medical_record_content_length_limit():
    with pytest.raises(ValidationError):
        MedicalRecord(content="x" * 16001)


def test_medical_record_defaults():
    rec = MedicalRecord(content="头痛两天")
    assert rec.tags == []
    assert rec.record_type == "visit"
