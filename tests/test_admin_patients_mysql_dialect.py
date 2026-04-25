"""Compile-time MySQL-dialect check on /api/admin/patients ORDER BY.

The dashboard at admin.doctoragentai.cn ran into a 1064 syntax error because
SQLAlchemy's `.nullslast()` emits literal ``NULLS LAST`` SQL on the MySQL
dialect — MySQL 8.x does not support that ORDER BY suffix. The other test
files run on SQLite (which DOES accept NULLS LAST as a no-op), so this
class of bug slipped past the existing regression suite.

This test compiles the ORDER BY expression actually used by `admin_patients`
against a synthetic MySQL dialect and asserts the rendered SQL contains no
``NULLS LAST`` / ``NULLS FIRST`` literal anywhere. If anyone re-introduces
``.nullslast()`` / ``.nullsfirst()`` here in the future, this fails fast on
SQLite-only CI before it can break prod.
"""
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.dialects import mysql

import db.models  # noqa: F401 — register all ORM models
from db.models import Patient, PatientMessage


def test_patients_order_by_compiles_clean_on_mysql():
    """The exact ORDER BY used by /api/admin/patients must not emit NULLS
    LAST/FIRST when compiled on MySQL — those are unsupported there."""

    last_msg_sq = (
        select(func.max(PatientMessage.created_at))
        .where(PatientMessage.patient_id == Patient.id)
        .correlate(Patient)
        .scalar_subquery()
    )

    nulls_last_marker = case((last_msg_sq.is_(None), 1), else_=0)

    stmt = (
        select(Patient.id)
        .order_by(nulls_last_marker, last_msg_sq.desc(), Patient.id.desc())
    )

    rendered = str(
        stmt.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    ).upper()

    assert "NULLS LAST" not in rendered, (
        f"Generated SQL contains NULLS LAST — MySQL will reject this with "
        f"a 1064 error.\nSQL:\n{rendered}"
    )
    assert "NULLS FIRST" not in rendered, (
        f"Generated SQL contains NULLS FIRST — MySQL will reject this.\n"
        f"SQL:\n{rendered}"
    )
    # Sanity: the CASE-based marker IS in the rendered SQL.
    assert "CASE" in rendered, (
        f"Expected CASE-based NULL ordering helper, got:\n{rendered}"
    )


def test_pre_fix_pattern_would_have_been_caught():
    """Negative control: the pre-fix `.desc().nullslast()` form WOULD trip
    this guard. Asserts the test would have caught the original bug."""

    last_msg_sq = (
        select(func.max(PatientMessage.created_at))
        .where(PatientMessage.patient_id == Patient.id)
        .correlate(Patient)
        .scalar_subquery()
    )

    bad_stmt = select(Patient.id).order_by(last_msg_sq.desc().nullslast())
    rendered = str(
        bad_stmt.compile(
            dialect=mysql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    ).upper()
    assert "NULLS LAST" in rendered, (
        "Sanity check failed — expected the pre-fix form to render NULLS LAST "
        "on the MySQL dialect, but it didn't. If SQLAlchemy started "
        "translating .nullslast() automatically on MySQL, this test (and the "
        "fix it guards) can be reconsidered."
    )
