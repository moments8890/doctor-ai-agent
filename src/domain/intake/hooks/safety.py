"""Neuro safety-screen hook. Keyword-based danger-signal screener.

Fires a doctor notification if any danger keyword appears in relevant
fields. Hook is best-effort — failures log and don't unwind persist.

Runs on both patient-mode and doctor-mode post-confirm. Distinct from
the full diagnosis pipeline (which is patient-only for medical templates)
and from any future therapy-intake crisis alert (which addresses
suicidality, not clinical danger signals).
"""
from __future__ import annotations

from domain.intake.protocols import PersistRef, SessionState
from domain.tasks.notifications import (
    send_doctor_notification as _send_doctor_notification,
)
from utils.log import log


_DANGER_KEYWORDS = (
    "突发剧烈头痛", "剧烈头痛", "意识障碍", "意识不清", "昏迷",
    "单侧肢体无力", "偏瘫", "偏身麻木", "言语不清", "失语", "构音障碍",
    "视物重影", "视物模糊", "复视", "抽搐", "癫痫发作",
    "喷射性呕吐", "颈项强直",
)
_SCAN_FIELDS = ("chief_complaint", "present_illness", "neuro_exam")


class SafetyScreenHook:
    name = "safety_screen"

    async def run(
        self,
        session: SessionState,
        ref: PersistRef,
        collected: dict[str, str],
    ) -> None:
        hits: list[tuple[str, str]] = []  # (field, keyword)
        for field_name in _SCAN_FIELDS:
            text = collected.get(field_name) or ""
            for kw in _DANGER_KEYWORDS:
                if kw in text:
                    hits.append((field_name, kw))

        if not hits:
            return

        patient_name = collected.get("_patient_name") or "患者"
        keywords = "、".join(sorted({kw for _, kw in hits}))
        body = (
            f"【危险信号】患者【{patient_name}】记录中出现神外危险信号："
            f"{keywords}。请尽快评估。记录 ID={ref.id}"
        )
        log(
            f"[safety] danger signals detected: doctor={session.doctor_id} "
            f"record={ref.id} hits={hits}"
        )
        try:
            await _send_doctor_notification(session.doctor_id, body)
        except Exception as e:
            log(
                f"[safety] notification failed (non-blocking): {e}",
                level="warning",
            )
