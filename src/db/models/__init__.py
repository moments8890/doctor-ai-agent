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
from db.models.runtime import RuntimeToken, SchedulerLease
from db.models.audit import AuditLog
from db.models.medical_record import MedicalRecord
from db.models.patient_message import PatientMessage
from db.models.interview_session import InterviewSessionDB, InterviewStatus
from db.models.doctor_chat_log import DoctorChatLog, ChatRole
from db.models.ai_suggestion import AISuggestion, SuggestionSection, SuggestionDecision
from db.models.knowledge_usage import KnowledgeUsageLog
from db.models.doctor_edit import DoctorEdit

__all__ = [
    "_utcnow",
    "DoctorKnowledgeItem",
    "Doctor", "InviteCode",
    "DoctorWechat",
    "Patient",
    "PatientAuth",
    "MedicalRecordDB", "RecordStatus",
    "DoctorTask", "TaskStatus", "TaskType",
    "RuntimeToken", "SchedulerLease",
    "AuditLog",
    "MedicalRecord",
    "PatientMessage",
    "InterviewSessionDB", "InterviewStatus",
    "DoctorChatLog", "ChatRole",
    "AISuggestion", "SuggestionSection", "SuggestionDecision",
    "KnowledgeUsageLog",
    "DoctorEdit",
]
