"""病历数据模型单元测试：验证 MedicalRecord Pydantic 模型的内容校验、长度限制和默认字段行为。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from db.models.medical_record import MedicalRecord


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
