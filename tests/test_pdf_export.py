"""PDF 导出服务测试：验证病历记录 PDF 生成的字节有效性及 PDF 格式头正确性。"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services.export.pdf_export import generate_records_pdf


def _make_record(content: str, tags=None, record_type: str = "visit", created_at=None):
    dt = created_at or datetime(2024, 3, 8, 10, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        content=content,
        tags=tags,
        record_type=record_type,
        created_at=dt,
    )


def test_generate_records_pdf_returns_bytes():
    records = [
        _make_record("血压 140/90，继续氨氯地平 5mg，3个月后随访。", tags='["高血压","氨氯地平5mg"]'),
        _make_record("复诊。血糖控制可，HbA1c 7.2%。", tags='["2型糖尿病","HbA1c7.2%"]'),
    ]
    pdf = generate_records_pdf(records=records, patient_name="张三", clinic_name="测试诊所")
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000
    # Valid PDF starts with %PDF
    assert pdf[:4] == b"%PDF"


def test_generate_records_pdf_single_record():
    records = [_make_record("初诊。高血压病史，建议规律服药。")]
    pdf = generate_records_pdf(records=records, patient_name="李四")
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


def test_generate_records_pdf_empty_content():
    records = [_make_record("", tags=None)]
    pdf = generate_records_pdf(records=records, patient_name="王五")
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


def test_generate_records_pdf_no_patient_name():
    records = [_make_record("匿名记录。")]
    pdf = generate_records_pdf(records=records)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
