"""
管理后台 UI 路由：提供患者列表、病历查看、系统提示和可观测性数据的 Web API。

All route handlers live in dedicated sub-modules; this file only assembles
the top-level router by including each sub-router.
"""

from __future__ import annotations

from fastapi import APIRouter

from channels.web.doctor_dashboard import debug_handlers as _debug_handlers
from channels.web.doctor_dashboard import invite_handlers as _invite_handlers
from channels.web.doctor_dashboard import admin_config as _admin_config
from channels.web.doctor_dashboard.patient_detail_handlers import router as _patient_detail_router
from channels.web.doctor_dashboard.record_edit_handlers import router as _record_edit_router
from channels.web.doctor_dashboard.profile_handlers import router as _profile_router
from channels.web.doctor_dashboard.onboarding_handlers import router as _onboarding_router
from channels.web.doctor_dashboard.knowledge_handlers import router as _knowledge_router
from channels.web.doctor_dashboard.persona_handlers import router as _persona_router
from channels.web.doctor_dashboard.persona_pending_handlers import router as _persona_pending_router
from channels.web.doctor_dashboard.kb_pending_handlers import router as _kb_pending_router
from channels.web.doctor_dashboard.hallucination_handlers import router as _hallucination_router
from channels.web.doctor_dashboard.briefing_handlers import router as _briefing_router
from channels.web.doctor_dashboard.diagnosis_handlers import router as _diagnosis_router
from channels.web.doctor_dashboard.knowledge_stats_handlers import router as _knowledge_stats_router
from channels.web.doctor_dashboard.teaching_handlers import router as _teaching_router
from channels.web.doctor_dashboard.draft_handlers import router as _draft_router
from channels.web.doctor_dashboard.ai_activity_handlers import router as _ai_activity_router
from channels.web.doctor_dashboard.review_queue_handlers import router as _review_queue_router
from channels.web.doctor_dashboard.admin_overview import router as _admin_overview_router
from channels.web.doctor_dashboard.admin_cleanup import router as _admin_cleanup_router
from channels.web.doctor_dashboard.admin_ops import router as _admin_ops_router
from channels.web.doctor_dashboard.admin_patients import router as _admin_patients_router
from channels.web.doctor_dashboard.admin_messages import router as _admin_messages_router
from channels.web.doctor_dashboard.admin_suggestions import router as _admin_suggestions_router
from channels.web.doctor_dashboard.preferences_handlers import router as _preferences_router
from channels.web.doctor_dashboard.today_summary_handlers import router as _today_summary_router
from channels.web.doctor_dashboard.feedback_handlers import router as _feedback_router

router = APIRouter(tags=["ui"])

# Existing sub-routers
router.include_router(_debug_handlers.router)
router.include_router(_invite_handlers.router)
router.include_router(_admin_config.router)

# Handler modules
router.include_router(_patient_detail_router)
router.include_router(_record_edit_router)
router.include_router(_profile_router)
router.include_router(_onboarding_router)
router.include_router(_knowledge_router)
router.include_router(_persona_router)
router.include_router(_persona_pending_router)
router.include_router(_kb_pending_router)
router.include_router(_hallucination_router)
router.include_router(_briefing_router)
router.include_router(_diagnosis_router)
router.include_router(_knowledge_stats_router)
router.include_router(_teaching_router)
router.include_router(_draft_router)
router.include_router(_ai_activity_router)
router.include_router(_review_queue_router)
router.include_router(_admin_overview_router)
router.include_router(_admin_cleanup_router)
router.include_router(_admin_ops_router)
router.include_router(_admin_patients_router)
router.include_router(_admin_messages_router)
router.include_router(_admin_suggestions_router)
router.include_router(_preferences_router)
router.include_router(_today_summary_router)
router.include_router(_feedback_router)
