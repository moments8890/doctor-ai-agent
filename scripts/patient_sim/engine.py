# scripts/patient_sim/engine.py
"""Simulation engine — runs one patient persona through the interview pipeline."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from scripts.patient_sim.patient_llm import PatientLLM


MAX_TURNS = 20
MIN_FIELDS_TO_STOP = 5
HTTP_TIMEOUT = 120.0


@dataclass
class SimResult:
    persona_id: str
    persona_name: str
    doctor_id: str
    session_id: Optional[str] = None
    record_id: Optional[int] = None
    review_id: Optional[int] = None
    patient_id: Optional[int] = None
    turns: int = 0
    final_collected: Dict[str, str] = field(default_factory=dict)
    final_progress: Dict[str, Any] = field(default_factory=dict)
    conversation: List[Dict[str, str]] = field(default_factory=list)
    error: Optional[str] = None


def _api(method: str, url: str, token: str = "", **kwargs) -> httpx.Response:
    headers = {}
    if token:
        headers["X-Patient-Token"] = token
    return httpx.request(method, url, headers=headers, timeout=HTTP_TIMEOUT, **kwargs)


def _ensure_test_doctor(server: str, doctor_id: str, db_path: str) -> None:
    """Create test doctor row if it doesn't exist (same as integration test pattern)."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT 1 FROM doctors WHERE doctor_id=?", (doctor_id,)).fetchone()
        if not row:
            from datetime import datetime
            now = datetime.utcnow().isoformat()
            conn.execute(
                "INSERT INTO doctors (doctor_id, name, channel, accepting_patients, department, created_at, updated_at) "
                "VALUES (?, ?, 'app', 1, '神经外科', ?, ?)",
                (doctor_id, f"模拟医生_{doctor_id[-4:]}", now, now),
            )
            conn.commit()
    finally:
        conn.close()


def run_persona(
    persona: Dict[str, Any],
    patient_llm: PatientLLM,
    server: str,
    db_path: str,
) -> SimResult:
    """Run full simulation for one persona. Returns SimResult."""
    doctor_id = f"intsim_{persona['id']}_{uuid.uuid4().hex[:6]}"
    result = SimResult(
        persona_id=persona["id"],
        persona_name=persona["name"],
        doctor_id=doctor_id,
    )

    try:
        # Setup
        _ensure_test_doctor(server, doctor_id, db_path)

        # Register
        phone = persona.get("phone", f"139{uuid.uuid4().hex[:8]}")
        resp = _api("POST", f"{server}/api/patient/register", json={
            "doctor_id": doctor_id,
            "name": persona["name"],
            "gender": persona.get("gender"),
            "year_of_birth": persona.get("year_of_birth"),
            "phone": phone,
        })
        if resp.status_code not in (200, 201):
            result.error = f"Register failed: {resp.status_code} {resp.text[:200]}"
            return result

        # Login
        resp = _api("POST", f"{server}/api/patient/login", json={
            "phone": phone,
            "year_of_birth": persona["year_of_birth"],
        })
        if resp.status_code != 200:
            result.error = f"Login failed: {resp.status_code} {resp.text[:200]}"
            return result
        token = resp.json()["token"]
        result.patient_id = resp.json().get("patient_id")

        # Start interview
        resp = _api("POST", f"{server}/api/patient/interview/start", token=token)
        if resp.status_code != 200:
            result.error = f"Start failed: {resp.status_code} {resp.text[:200]}"
            return result
        data = resp.json()
        result.session_id = data["session_id"]
        system_reply = data.get("reply", "")

        # Interview loop
        conversation = []
        for turn_num in range(MAX_TURNS):
            # Patient LLM responds
            patient_text = patient_llm.respond(persona, conversation, system_reply)

            conversation.append({"role": "assistant", "content": system_reply})
            conversation.append({"role": "user", "content": patient_text})

            # Send to system
            resp = _api("POST", f"{server}/api/patient/interview/turn", token=token, json={
                "session_id": result.session_id,
                "text": patient_text,
            })
            if resp.status_code != 200:
                result.error = f"Turn {turn_num+1} failed: {resp.status_code} {resp.text[:200]}"
                break

            data = resp.json()
            system_reply = data.get("reply", "")
            result.final_collected = data.get("collected", {})
            result.final_progress = data.get("progress", {})
            result.turns = turn_num + 1

            # Stop conditions
            filled = result.final_progress.get("filled", 0)
            status = data.get("status", "interviewing")
            if filled >= MIN_FIELDS_TO_STOP or status != "interviewing":
                break

        result.conversation = conversation

        # Confirm
        if result.error is None:
            resp = _api("POST", f"{server}/api/patient/interview/confirm", token=token, json={
                "session_id": result.session_id,
            })
            if resp.status_code == 200:
                confirm_data = resp.json()
                result.record_id = confirm_data.get("record_id")
                result.review_id = confirm_data.get("review_id")
            else:
                result.error = f"Confirm failed: {resp.status_code} {resp.text[:200]}"

    except Exception as exc:
        result.error = f"Exception: {exc}"

    return result
