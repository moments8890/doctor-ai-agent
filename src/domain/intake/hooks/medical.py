"""Medical template post-confirm hooks.

Each hook wraps one existing side effect from the pre-Phase-1 confirm paths.
Failures are logged and swallowed — the engine treats hooks as best-effort.
"""
from __future__ import annotations

from db.crud.patient import get_patient_for_doctor as _get_patient_for_doctor
from db.engine import AsyncSessionLocal
from domain.diagnosis_pipeline import run_diagnosis as _run_diagnosis
from domain.intake.protocols import PersistRef, SessionState
from domain.tasks.from_record import (
    generate_tasks_from_record as _generate_tasks_from_record,
)
from domain.tasks.notifications import (
    send_doctor_notification as _send_doctor_notification,
)
from utils.log import log, safe_create_task as _safe_create_task


class TriggerDiagnosisPipelineHook:
    name = "trigger_diagnosis_pipeline"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        try:
            _safe_create_task(
                _run_diagnosis(doctor_id=session.doctor_id, record_id=ref.id),
                name=f"diagnosis-{ref.id}",
            )
            log(f"[intake] diagnosis triggered for record={ref.id}")
        except Exception as e:
            log(f"[intake] diagnosis trigger failed: {e}", level="warning")


class NotifyDoctorHook:
    name = "notify_doctor"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        try:
            patient_name = collected.get("_patient_name") or "患者"
            await _send_doctor_notification(
                session.doctor_id,
                f"患者【{patient_name}】已完成预问诊，请查看待审核记录。",
            )
        except Exception as e:
            log(f"[intake] doctor notification failed: {e}", level="warning")


class GenerateFollowupTasksHook:
    name = "generate_followup_tasks"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        try:
            async with AsyncSessionLocal() as db:
                patient = await _get_patient_for_doctor(
                    db, session.doctor_id, session.patient_id,
                )
            patient_name = patient.name if patient else ""
            task_ids = await _generate_tasks_from_record(
                doctor_id=session.doctor_id,
                patient_id=session.patient_id,
                record_id=ref.id,
                orders_followup=collected.get("orders_followup"),
                treatment_plan=collected.get("treatment_plan"),
                patient_name=patient_name,
            )
            if task_ids:
                log(
                    f"[intake-confirm] auto-created {len(task_ids)} "
                    f"follow-up tasks: {task_ids}"
                )
        except Exception as e:
            log(
                f"[intake-confirm] task generation failed "
                f"(non-blocking): {e}",
                level="warning",
            )
