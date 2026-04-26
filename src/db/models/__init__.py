"""ORM model registry."""
from db.models.base import _utcnow
from db.models.doctor import (
    DoctorKnowledgeItem,
    Doctor, InviteCode,
)
from db.models.doctor_wechat import DoctorWechat
from db.models.patient import Patient
from db.models.patient_auth import PatientAuth
from db.models.records import MedicalRecordDB, RecordStatus
from db.models.tasks import DoctorTask, TaskStatus, TaskType
from db.models.runtime import RuntimeToken
from db.models.audit import AuditLog
from db.models.medical_record import MedicalRecord
from db.models.patient_message import PatientMessage
from db.models.intake_session import IntakeSessionDB, IntakeStatus
from db.models.doctor_chat_log import DoctorChatLog, ChatRole
from db.models.ai_suggestion import (
    AISuggestion,
    SuggestionSection,
    SuggestionDecision,
    FeedbackReasonTag,
    FeedbackDoctorAction,
)
from db.models.knowledge_usage import KnowledgeUsageLog
from db.models.doctor_edit import DoctorEdit
from db.models.doctor_persona import DoctorPersona, EMPTY_PERSONA_FIELDS
from db.models.persona_pending import PersonaPendingItem
from db.models.kb_pending import KbPendingItem
from db.models.message_draft import MessageDraft, DraftStatus
from db.models.user_preferences import UserPreferences, DEFAULT_PREFERENCES
from db.models.form_response import FormResponseDB
from db.models.feature_flag import DoctorFeatureFlag
from db.models.platform_feedback import PlatformFeedback

__all__ = [
    "_utcnow",
    "DoctorKnowledgeItem",
    "Doctor", "InviteCode",
    "DoctorWechat",
    "Patient",
    "PatientAuth",
    "MedicalRecordDB", "RecordStatus",
    "DoctorTask", "TaskStatus", "TaskType",
    "RuntimeToken",
    "AuditLog",
    "MedicalRecord",
    "PatientMessage",
    "IntakeSessionDB", "IntakeStatus",
    "DoctorChatLog", "ChatRole",
    "AISuggestion", "SuggestionSection", "SuggestionDecision",
    "FeedbackReasonTag", "FeedbackDoctorAction",
    "KnowledgeUsageLog",
    "DoctorEdit",
    "DoctorPersona", "EMPTY_PERSONA_FIELDS",
    "PersonaPendingItem",
    "KbPendingItem",
    "MessageDraft", "DraftStatus",
    "UserPreferences", "DEFAULT_PREFERENCES",
    "FormResponseDB",
    "DoctorFeatureFlag",
    "PlatformFeedback",
]
