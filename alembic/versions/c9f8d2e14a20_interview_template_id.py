"""Interview template_id + form_responses + retire draft_created.

Phase 0 of the interview-pipeline-extensibility work. See the spec at
docs/superpowers/specs/2026-04-22-interview-pipeline-extensibility-design.md
§4a. Additive only — zero behavior change. Existing sessions backfill to
medical_general_v1.

Revision ID: c9f8d2e14a20
Revises: a3f8c912de75
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9f8d2e14a20"
down_revision = "a3f8c912de75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. interview_sessions.template_id — server_default fills existing rows,
    #    NOT NULL guarantees every session has a template going forward.
    op.add_column(
        "interview_sessions",
        sa.Column(
            "template_id",
            sa.String(64),
            nullable=False,
            server_default="medical_general_v1",
        ),
    )
    op.create_index(
        "ix_interview_template", "interview_sessions", ["template_id"],
    )

    # 2. doctors.preferred_template_id — NULL means "follow current default".
    op.add_column(
        "doctors",
        sa.Column("preferred_template_id", sa.String(64), nullable=True),
    )

    # 3. Retire draft_created. The enum value was only read by
    #    admin_overview.py:145; we flip it to confirmed so the 7-day
    #    "completed" metric stays continuous.
    # NOTE: This data migration is irreversible. downgrade() restores the
    # schema but cannot reconstruct which rows were draft_created before
    # this migration — take a DB backup before running in production.
    op.execute(
        "UPDATE interview_sessions SET status='confirmed' "
        "WHERE status='draft_created'"
    )

    # 4. New form_responses table.
    op.create_table(
        "form_responses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "doctor_id",
            sa.String(64),
            sa.ForeignKey("doctors.doctor_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            sa.Integer,
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("interview_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="draft"
        ),
        sa.Column(
            "created_at", sa.DateTime, nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime, nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_form_response_doctor_patient_template",
        "form_responses",
        ["doctor_id", "patient_id", "template_id"],
    )
    op.create_index(
        "ix_form_response_patient_template_created",
        "form_responses",
        ["patient_id", "template_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_form_response_patient_template_created", "form_responses",
    )
    op.drop_index(
        "ix_form_response_doctor_patient_template", "form_responses",
    )
    op.drop_table("form_responses")
    op.drop_column("doctors", "preferred_template_id")
    op.drop_index("ix_interview_template", "interview_sessions")
    op.drop_column("interview_sessions", "template_id")
