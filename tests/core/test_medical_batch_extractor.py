"""MedicalBatchExtractor — delegates to batch_extract_from_transcript."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from domain.intake.templates.medical_general import MedicalBatchExtractor


@pytest.mark.asyncio
async def test_extract_delegates_with_patient_info_rename():
    # Phase 2: import is now lazy (inside extract()) to avoid circular import;
    # patch the function at its source module rather than via the old alias.
    with patch(
        "domain.patients.intake_summary.batch_extract_from_transcript",
        new=AsyncMock(return_value={"chief_complaint": "头痛"}),
    ) as mock_batch:
        be = MedicalBatchExtractor()
        out = await be.extract(
            conversation=[{"role": "user", "content": "头痛"}],
            context={"name": "张三", "gender": "男", "age": "45"},
            mode="doctor",
        )

    mock_batch.assert_called_once_with(
        [{"role": "user", "content": "头痛"}],
        {"name": "张三", "gender": "男", "age": "45"},
        mode="doctor",
    )
    assert out == {"chief_complaint": "头痛"}


@pytest.mark.asyncio
async def test_extract_propagates_none_on_empty_result():
    with patch(
        "domain.patients.intake_summary.batch_extract_from_transcript",
        new=AsyncMock(return_value=None),
    ):
        be = MedicalBatchExtractor()
        out = await be.extract(
            conversation=[], context={}, mode="patient",
        )
    assert out is None
