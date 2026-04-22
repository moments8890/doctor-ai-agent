"""Drop 13 ghost tables — schema drift cleanup.

These tables exist in the prod DB but have no ORM model in src/db/models/
and no non-test code references. All were introduced by earlier migrations
(mostly 2026-03-10), never populated (table_rows=0 and update_time=NULL at
audit time), and orphaned when the features they supported were scoped out.

Dropped tables and their original purpose (for future archaeologists):

  doctor_session_states   — short-lived per-doctor conversation state; replaced
                            by interview_sessions.
  pending_records         — ADR 0012 pending-draft flow, since replaced.
  pending_messages        — async WeChat message queue; the recover_stale
                            function is now a no-op stub kept for import
                            compatibility.
  patient_label_assignments, patient_labels — label feature cut from MVP.
  doctor_conversation_turns — superseded by doctor_chat_log (itself also empty).
  specialty_scores        — ML specialty-routing experiment.
  doctor_notify_preferences — notifications deferred (D6.6 in feature matrix).
  runtime_configs         — superseded by config/runtime.json file-based config.
  medical_record_versions — versioning never implemented.
  patient_chat_log        — superseded by patient_messages.
  medical_record_exports  — exports now computed on-demand, not persisted.
  neuro_cvd_context       — remnant of specialty-switching experiment.

Drop order honours FK dependencies (children before parents).

Downgrade recreates all 13 with their exact prod DDL (captured via
`SHOW CREATE TABLE` at 2026-04-22). Rows are not restored — all tables were
empty at drop time. If a future migration needs one of these tables back
with data, restore from a pre-migration backup.

Revision ID: a3f8c912de75
Revises: b5e7d21a4c83
Create Date: 2026-04-22
"""

from __future__ import annotations

from alembic import op


revision = "a3f8c912de75"
down_revision = "b5e7d21a4c83"
branch_labels = None
depends_on = None


# Drop order: children (tables with FKs to another in this set) first.
_DROP_ORDER = [
    "doctor_session_states",      # FK → pending_records
    "patient_label_assignments",  # FK → patient_labels
    "pending_records",
    "patient_labels",
    "pending_messages",
    "doctor_conversation_turns",
    "specialty_scores",
    "doctor_notify_preferences",
    "runtime_configs",
    "medical_record_versions",
    "patient_chat_log",
    "medical_record_exports",
    "neuro_cvd_context",
]


def upgrade() -> None:
    for table in _DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table}")


# DDL captured from prod 2026-04-22 via SHOW CREATE TABLE. Create order is
# the reverse of drop order — parents before children.
_RECREATE_DDL = {
    "neuro_cvd_context": """
        CREATE TABLE neuro_cvd_context (
          id int NOT NULL AUTO_INCREMENT,
          record_id int NOT NULL,
          patient_id int DEFAULT NULL,
          doctor_id varchar(64) NOT NULL,
          diagnosis_subtype varchar(32) DEFAULT NULL,
          surgery_status varchar(16) DEFAULT NULL,
          source varchar(16) DEFAULT NULL,
          raw_json text,
          created_at datetime NOT NULL,
          updated_at datetime DEFAULT NULL,
          PRIMARY KEY (id),
          KEY ix_neuro_cvd_record_id (record_id),
          KEY ix_neuro_cvd_doctor_patient (doctor_id, patient_id),
          KEY ix_neuro_cvd_patient_ts (patient_id, created_at),
          CONSTRAINT neuro_cvd_context_ibfk_1 FOREIGN KEY (record_id) REFERENCES medical_records (id) ON DELETE CASCADE,
          CONSTRAINT neuro_cvd_context_ibfk_2 FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE SET NULL,
          CONSTRAINT neuro_cvd_context_ibfk_3 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "medical_record_exports": """
        CREATE TABLE medical_record_exports (
          id int NOT NULL AUTO_INCREMENT,
          record_id int NOT NULL,
          doctor_id varchar(64) NOT NULL,
          export_format varchar(16) DEFAULT NULL,
          exported_at datetime NOT NULL,
          pdf_hash varchar(256) DEFAULT NULL,
          created_at datetime NOT NULL,
          PRIMARY KEY (id),
          KEY ix_record_exports_record_id (record_id),
          KEY ix_record_exports_doctor_exported (doctor_id, exported_at),
          KEY ix_record_exports_record_exported (record_id, exported_at),
          CONSTRAINT medical_record_exports_ibfk_1 FOREIGN KEY (record_id) REFERENCES medical_records (id) ON DELETE CASCADE,
          CONSTRAINT medical_record_exports_ibfk_2 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "patient_chat_log": """
        CREATE TABLE patient_chat_log (
          id int NOT NULL AUTO_INCREMENT,
          patient_id int NOT NULL,
          doctor_id varchar(64) NOT NULL,
          session_id varchar(36) NOT NULL,
          role varchar(16) NOT NULL,
          content text NOT NULL,
          direction varchar(16) NOT NULL,
          source varchar(16) DEFAULT NULL,
          sender_id varchar(64) DEFAULT NULL,
          triage_category varchar(32) DEFAULT NULL,
          ai_handled tinyint(1) DEFAULT '1',
          created_at datetime NOT NULL,
          PRIMARY KEY (id),
          KEY doctor_id (doctor_id),
          KEY ix_patient_chat_log_session (session_id, created_at),
          KEY ix_patient_chat_log_session_id (session_id),
          KEY ix_patient_chat_log_patient (patient_id, created_at),
          CONSTRAINT patient_chat_log_ibfk_1 FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE CASCADE,
          CONSTRAINT patient_chat_log_ibfk_2 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "medical_record_versions": """
        CREATE TABLE medical_record_versions (
          id int NOT NULL AUTO_INCREMENT,
          record_id int NOT NULL,
          doctor_id varchar(64) NOT NULL,
          old_content text,
          old_tags text,
          old_record_type varchar(32) DEFAULT NULL,
          changed_at datetime NOT NULL,
          PRIMARY KEY (id),
          KEY doctor_id (doctor_id),
          KEY ix_record_versions_record_doctor_changed (record_id, doctor_id, changed_at),
          CONSTRAINT medical_record_versions_ibfk_1 FOREIGN KEY (record_id) REFERENCES medical_records (id) ON DELETE CASCADE,
          CONSTRAINT medical_record_versions_ibfk_2 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "runtime_configs": """
        CREATE TABLE runtime_configs (
          config_key varchar(64) NOT NULL,
          content_json text NOT NULL,
          updated_at datetime NOT NULL,
          PRIMARY KEY (config_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "doctor_notify_preferences": """
        CREATE TABLE doctor_notify_preferences (
          doctor_id varchar(64) NOT NULL,
          notify_mode varchar(16) NOT NULL DEFAULT 'auto',
          schedule_type varchar(16) NOT NULL DEFAULT 'immediate',
          interval_minutes int NOT NULL DEFAULT 1,
          cron_expr varchar(64) DEFAULT NULL,
          last_auto_run_at datetime DEFAULT NULL,
          updated_at datetime NOT NULL,
          PRIMARY KEY (doctor_id),
          CONSTRAINT doctor_notify_preferences_ibfk_1 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "specialty_scores": """
        CREATE TABLE specialty_scores (
          id int NOT NULL AUTO_INCREMENT,
          record_id int NOT NULL,
          doctor_id varchar(64) NOT NULL,
          score_type varchar(32) NOT NULL,
          score_value float DEFAULT NULL,
          raw_text varchar(256) DEFAULT NULL,
          details_json text,
          patient_id int DEFAULT NULL,
          source varchar(16) NOT NULL DEFAULT 'chat',
          extracted_at datetime DEFAULT NULL,
          created_at datetime NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uq_specialty_scores_record_type (record_id, score_type),
          KEY ix_specialty_scores_record_id (record_id),
          KEY ix_specialty_scores_doctor_id (doctor_id),
          KEY ix_specialty_scores_patient_score_ts (patient_id, score_type, extracted_at),
          KEY ix_specialty_scores_doctor_type_ts (doctor_id, score_type, extracted_at),
          CONSTRAINT specialty_scores_ibfk_1 FOREIGN KEY (record_id) REFERENCES medical_records (id) ON DELETE CASCADE,
          CONSTRAINT specialty_scores_ibfk_2 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE,
          CONSTRAINT specialty_scores_ibfk_3 FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "doctor_conversation_turns": """
        CREATE TABLE doctor_conversation_turns (
          id int NOT NULL AUTO_INCREMENT,
          doctor_id varchar(64) NOT NULL,
          role varchar(16) NOT NULL,
          content text NOT NULL,
          created_at datetime NOT NULL,
          PRIMARY KEY (id),
          KEY ix_turns_doctor_created (doctor_id, created_at),
          CONSTRAINT doctor_conversation_turns_ibfk_1 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "pending_messages": """
        CREATE TABLE pending_messages (
          id varchar(64) NOT NULL,
          doctor_id varchar(64) NOT NULL,
          raw_content text NOT NULL,
          status varchar(16) NOT NULL DEFAULT 'pending',
          created_at datetime NOT NULL,
          attempt_count int NOT NULL DEFAULT 0,
          PRIMARY KEY (id),
          KEY ix_pending_messages_status_created (status, created_at),
          KEY ix_pending_messages_doctor (doctor_id),
          CONSTRAINT pending_messages_ibfk_1 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE,
          CONSTRAINT ck_pending_messages_status CHECK (status IN ('pending', 'done', 'dead'))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "patient_labels": """
        CREATE TABLE patient_labels (
          id int NOT NULL AUTO_INCREMENT,
          doctor_id varchar(64) NOT NULL,
          name varchar(64) NOT NULL,
          color varchar(16) DEFAULT NULL,
          created_at datetime NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uq_labels_doctor_name (doctor_id, name),
          KEY ix_labels_doctor_created (doctor_id, created_at),
          CONSTRAINT patient_labels_ibfk_1 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "pending_records": """
        CREATE TABLE pending_records (
          id varchar(64) NOT NULL,
          doctor_id varchar(64) NOT NULL,
          patient_id int DEFAULT NULL,
          patient_name varchar(128) DEFAULT NULL,
          draft_json text NOT NULL,
          status varchar(32) NOT NULL DEFAULT 'awaiting',
          created_at datetime NOT NULL,
          expires_at datetime NOT NULL,
          PRIMARY KEY (id),
          KEY patient_id (patient_id),
          KEY ix_pending_records_expires (expires_at),
          KEY ix_pending_records_status_expires (status, expires_at),
          KEY ix_pending_records_doctor_status_expires (doctor_id, status, expires_at),
          CONSTRAINT pending_records_ibfk_1 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE,
          CONSTRAINT pending_records_ibfk_2 FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE SET NULL,
          CONSTRAINT ck_pending_records_status CHECK (status IN ('awaiting', 'confirmed', 'abandoned', 'expired'))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "patient_label_assignments": """
        CREATE TABLE patient_label_assignments (
          patient_id int NOT NULL,
          label_id int NOT NULL,
          PRIMARY KEY (patient_id, label_id),
          KEY label_id (label_id),
          CONSTRAINT patient_label_assignments_ibfk_1 FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE CASCADE,
          CONSTRAINT patient_label_assignments_ibfk_2 FOREIGN KEY (label_id) REFERENCES patient_labels (id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    "doctor_session_states": """
        CREATE TABLE doctor_session_states (
          doctor_id varchar(64) NOT NULL,
          current_patient_id int DEFAULT NULL,
          pending_create_name varchar(128) DEFAULT NULL,
          pending_record_id varchar(64) DEFAULT NULL,
          interview_json text,
          cvd_scale_json text,
          updated_at datetime NOT NULL,
          PRIMARY KEY (doctor_id),
          KEY current_patient_id (current_patient_id),
          KEY pending_record_id (pending_record_id),
          CONSTRAINT doctor_session_states_ibfk_1 FOREIGN KEY (doctor_id) REFERENCES doctors (doctor_id) ON DELETE CASCADE,
          CONSTRAINT doctor_session_states_ibfk_2 FOREIGN KEY (current_patient_id) REFERENCES patients (id) ON DELETE SET NULL,
          CONSTRAINT doctor_session_states_ibfk_3 FOREIGN KEY (pending_record_id) REFERENCES pending_records (id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
}


def downgrade() -> None:
    # Recreate in reverse of drop order — parents before children.
    for table in reversed(_DROP_ORDER):
        op.execute(_RECREATE_DDL[table])
