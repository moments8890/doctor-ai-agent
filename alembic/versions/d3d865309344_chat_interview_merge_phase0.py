"""chat_interview_merge_phase0

Adds dedup/provenance/safety columns to medical_records, doctor_knowledge_items,
doctors, and patient_messages. Schema for the new FieldEntryDB and RecordSupplementDB
tables is in the next migration step.

Revision ID: d3d865309344
Revises: b8c9d0e1f234
Create Date: 2026-04-25 14:58:11.227022
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3d865309344'
down_revision = 'b8c9d0e1f234'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MedicalRecordDB additions
    op.add_column("medical_records", sa.Column("extraction_confidence", sa.Float, nullable=True))
    op.add_column("medical_records", sa.Column("patient_confirmed_at", sa.DateTime, nullable=True))
    op.add_column("medical_records", sa.Column("cancellation_reason", sa.String(64), nullable=True))
    op.add_column("medical_records", sa.Column("red_flag", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("medical_records", sa.Column("intake_segment_id", sa.String(64), nullable=True))
    op.add_column("medical_records", sa.Column("dedup_skipped_by_patient", sa.Boolean, nullable=False, server_default=sa.false()))
    op.create_index("ix_medical_records_intake_segment_id", "medical_records", ["intake_segment_id"])

    # DoctorKnowledgeItem additions
    op.add_column("doctor_knowledge_items", sa.Column("patient_safe", sa.Boolean, nullable=False, server_default=sa.false()))

    # Doctor additions
    op.add_column("doctors", sa.Column("kb_curation_onboarding_done", sa.Boolean, nullable=False, server_default=sa.false()))

    # PatientMessage additions
    op.add_column("patient_messages", sa.Column("retracted", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("patient_messages", "retracted")
    op.drop_column("doctors", "kb_curation_onboarding_done")
    op.drop_column("doctor_knowledge_items", "patient_safe")
    op.drop_index("ix_medical_records_intake_segment_id", table_name="medical_records")
    for col in ("dedup_skipped_by_patient", "intake_segment_id", "red_flag",
                "cancellation_reason", "patient_confirmed_at", "extraction_confidence"):
        op.drop_column("medical_records", col)
