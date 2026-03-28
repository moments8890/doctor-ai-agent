"""
管理后台 UI 路由：提供患者列表、病历查看、系统提示和可观测性数据的 Web API。

All route handlers live in dedicated sub-modules; this file only assembles
the top-level router by including each sub-router.
"""

from __future__ import annotations

from fastapi import APIRouter

from channels.web.ui import debug_handlers as _debug_handlers
from channels.web.ui import invite_handlers as _invite_handlers
from channels.web.ui import admin_config as _admin_config
from channels.web.ui.patient_detail_handlers import router as _patient_detail_router
from channels.web.ui.record_edit_handlers import router as _record_edit_router
from channels.web.ui.doctor_profile_handlers import router as _doctor_profile_router
from channels.web.ui.knowledge_handlers import router as _knowledge_router
from channels.web.ui.briefing_handlers import router as _briefing_router
from channels.web.ui.diagnosis_handlers import router as _diagnosis_router
from channels.web.ui.knowledge_stats_handlers import router as _knowledge_stats_router
from channels.web.ui.teaching_handlers import router as _teaching_router
from channels.web.ui.draft_handlers import router as _draft_router
from channels.web.ui.ai_activity_handlers import router as _ai_activity_router
from channels.web.ui.review_queue_handlers import router as _review_queue_router

router = APIRouter(tags=["ui"])

# Existing sub-routers
router.include_router(_debug_handlers.router)
router.include_router(_invite_handlers.router)
router.include_router(_admin_config.router)

# Handler modules
router.include_router(_patient_detail_router)
router.include_router(_record_edit_router)
router.include_router(_doctor_profile_router)
router.include_router(_knowledge_router)
router.include_router(_briefing_router)
router.include_router(_diagnosis_router)
router.include_router(_knowledge_stats_router)
router.include_router(_teaching_router)
router.include_router(_draft_router)
router.include_router(_ai_activity_router)
router.include_router(_review_queue_router)
