"""db.crud 包初始化：聚合所有 CRUD 子模块的公开接口。"""
from db.crud._common import _utcnow
from db.crud.doctor import (
    _resolve_doctor_id,
    _ensure_doctor_exists,
    get_doctor_by_id,
    get_doctor_wechat_user_id,
    get_doctor_mini_openid,
    get_doctor_by_mini_openid,
    link_mini_openid,
    add_doctor_knowledge_item,
    list_doctor_knowledge_items,
)
from db.crud.patient import (
    get_patient_for_doctor,
    create_patient,
    set_patient_access_code,
    find_patient_by_name,
    find_patients_by_exact_name,
    delete_patient_for_doctor,
    get_all_patients,
    update_patient_demographics,
)
from db.crud.records import (
    save_record,
    get_records_for_patient,
    get_all_records_for_doctor,
    count_records_for_doctor,
    update_latest_record_for_patient,
)
from db.crud.tasks import (
    create_task,
    list_tasks,
    update_task_status,
    get_task_by_id,
    update_task_due_at,
    get_due_tasks,
    mark_task_notified,
    revert_task_to_pending,
    update_task_notes,
)
from db.crud.runtime import (
    get_runtime_token,
    upsert_runtime_token,
    try_acquire_scheduler_lease,
    release_scheduler_lease,
)
from db.crud.patient_message import (
    save_patient_message,
    list_patient_messages,
)
from db.crud.retention import (
    archive_old_audit_logs,
    cleanup_chat_log,
)
from db.crud.suggestions import (
    create_suggestion,
    get_suggestions_for_record,
    get_suggestion_by_id,
    update_decision,
    has_suggestions,
)

__all__ = [
    # doctor
    "_ensure_doctor_exists",
    "get_doctor_by_id",
    "get_doctor_wechat_user_id",
    "get_doctor_mini_openid",
    "get_doctor_by_mini_openid",
    "link_mini_openid",
    "add_doctor_knowledge_item",
    "list_doctor_knowledge_items",
    # patient
    "get_patient_for_doctor",
    "create_patient",
    "set_patient_access_code",
    "find_patient_by_name",
    "find_patients_by_exact_name",
    "delete_patient_for_doctor",
    "get_all_patients",
    "update_patient_demographics",
    # records
    "save_record",
    "get_records_for_patient",
    "get_all_records_for_doctor",
    "count_records_for_doctor",
    "update_latest_record_for_patient",
    # tasks
    "create_task",
    "list_tasks",
    "update_task_status",
    "get_task_by_id",
    "update_task_due_at",
    "get_due_tasks",
    "mark_task_notified",
    "revert_task_to_pending",
    "update_task_notes",
    # runtime
    "get_runtime_token",
    "upsert_runtime_token",
    "try_acquire_scheduler_lease",
    "release_scheduler_lease",
    # patient_message
    "save_patient_message",
    "list_patient_messages",
    # retention
    "archive_old_audit_logs",
    "cleanup_chat_log",
    # suggestions
    "create_suggestion",
    "get_suggestions_for_record",
    "get_suggestion_by_id",
    "update_decision",
    "has_suggestions",
]
