"""Unit tests for services/domain/patient_ops.py — resolve_patient."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.domain.patient_ops import resolve_patient


def _make_patient(
    id: int = 1,
    name: str = "张三",
    gender: str = "男",
    year_of_birth: int = 1990,
    doctor_id: str = "doc1",
):
    return SimpleNamespace(
        id=id, name=name, gender=gender, year_of_birth=year_of_birth,
        doctor_id=doctor_id,
    )


@pytest.mark.asyncio
async def test_resolve_patient_creates_when_not_found():
    """When find returns None, a new patient is created."""
    new_patient = _make_patient()
    session = AsyncMock()

    with patch("services.domain.patient_ops.find_patient_by_name", new_callable=AsyncMock, return_value=None) as mock_find, \
         patch("services.domain.patient_ops.create_patient", new_callable=AsyncMock, return_value=new_patient) as mock_create:
        patient, was_created = await resolve_patient(session, "doc1", "张三", gender="男", age=34)

    assert was_created is True
    assert patient is new_patient
    mock_find.assert_awaited_once_with(session, "doc1", "张三")
    mock_create.assert_awaited_once_with(session, "doc1", "张三", "男", 34)


@pytest.mark.asyncio
async def test_resolve_patient_returns_existing_no_update():
    """When the patient exists and demographics match, no commit occurs."""
    existing = _make_patient(gender="男", year_of_birth=1990)
    session = AsyncMock()

    with patch("services.domain.patient_ops.find_patient_by_name", new_callable=AsyncMock, return_value=existing):
        patient, was_created = await resolve_patient(session, "doc1", "张三", gender="男", age=None)

    assert was_created is False
    assert patient is existing
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_patient_updates_gender():
    """When gender differs, demographic correction triggers a commit."""
    existing = _make_patient(gender="男", year_of_birth=1990)
    session = AsyncMock()

    with patch("services.domain.patient_ops.find_patient_by_name", new_callable=AsyncMock, return_value=existing):
        patient, was_created = await resolve_patient(session, "doc1", "张三", gender="女")

    assert was_created is False
    assert patient.gender == "女"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_patient_updates_year_of_birth():
    """When age is provided and year_of_birth differs, it is updated."""
    existing = _make_patient(year_of_birth=1990)
    session = AsyncMock()

    with patch("services.domain.patient_ops.find_patient_by_name", new_callable=AsyncMock, return_value=existing), \
         patch("db.repositories.patients._year_of_birth", return_value=2000):
        patient, was_created = await resolve_patient(session, "doc1", "张三", age=26)

    assert was_created is False
    assert patient.year_of_birth == 2000
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_patient_no_update_when_yob_matches():
    """When _year_of_birth returns the same value, no commit occurs."""
    existing = _make_patient(year_of_birth=1990)
    session = AsyncMock()

    with patch("services.domain.patient_ops.find_patient_by_name", new_callable=AsyncMock, return_value=existing), \
         patch("db.repositories.patients._year_of_birth", return_value=1990):
        patient, was_created = await resolve_patient(session, "doc1", "张三", age=36)

    assert was_created is False
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_patient_no_update_when_yob_is_none():
    """When _year_of_birth returns None, no update occurs."""
    existing = _make_patient(year_of_birth=1990)
    session = AsyncMock()

    with patch("services.domain.patient_ops.find_patient_by_name", new_callable=AsyncMock, return_value=existing), \
         patch("db.repositories.patients._year_of_birth", return_value=None):
        patient, was_created = await resolve_patient(session, "doc1", "张三", age=0)

    assert was_created is False
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_patient_invalid_gender_ignored():
    """Gender values other than 男/女 are ignored."""
    existing = _make_patient(gender="男")
    session = AsyncMock()

    with patch("services.domain.patient_ops.find_patient_by_name", new_callable=AsyncMock, return_value=existing):
        patient, was_created = await resolve_patient(session, "doc1", "张三", gender="unknown")

    assert was_created is False
    assert patient.gender == "男"  # unchanged
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_patient_both_demographics_updated():
    """Both gender and year_of_birth updated in a single call."""
    existing = _make_patient(gender="男", year_of_birth=1990)
    session = AsyncMock()

    with patch("services.domain.patient_ops.find_patient_by_name", new_callable=AsyncMock, return_value=existing), \
         patch("db.repositories.patients._year_of_birth", return_value=2000):
        patient, was_created = await resolve_patient(session, "doc1", "张三", gender="女", age=26)

    assert was_created is False
    assert patient.gender == "女"
    assert patient.year_of_birth == 2000
    session.commit.assert_awaited_once()
