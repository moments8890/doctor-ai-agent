"""Background-task wrapper around ``regenerate_patient_summary``.

``save_record`` fires this via ``asyncio.create_task`` so the LLM call doesn't
block the record save. The task owns its own DB session and swallows errors —
a failed summary regeneration must never bubble up and fail the record save.

Concurrent-call dedup: if a regen is already in-flight for a given patient,
further calls short-circuit. This prevents two fast record-saves from firing
two parallel LLM calls for the same patient.
"""
from __future__ import annotations

import asyncio
from typing import Set

from db.engine import AsyncSessionLocal
from domain.briefing.patient_summary import regenerate_patient_summary
from utils.log import log


# Patients with an in-flight regen task. Module-level set → per-process lock.
_in_flight: Set[int] = set()
_in_flight_lock = asyncio.Lock()


async def schedule_patient_summary_refresh(patient_id: int) -> None:
    async with _in_flight_lock:
        if patient_id in _in_flight:
            log(f"[patient_summary_bg] skip patient={patient_id} (in-flight)")
            return
        _in_flight.add(patient_id)

    try:
        async with AsyncSessionLocal() as session:
            await regenerate_patient_summary(patient_id=patient_id, db=session)
            await session.commit()
    except Exception as e:  # noqa: BLE001 — must never fail record save
        log(f"[patient_summary_bg] failed patient={patient_id}: {e}")
    finally:
        async with _in_flight_lock:
            _in_flight.discard(patient_id)
