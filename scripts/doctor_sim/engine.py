"""Simulation engine — runs one doctor persona through the doctor interview pipeline.

Doctor personas use scripted turn_plan (no LLM generation needed).
Each turn is sent as Form data to POST /api/records/interview/turn.
After all turns, calls POST /api/records/interview/confirm.
"""
from __future__ import annotations

import sqlite3
from typing import Optional
from uuid import uuid4

import httpx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_doctor(db_path: str, doctor_id: str) -> None:
    """Insert a test doctor row if it does not already exist."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO doctors (doctor_id, name, specialty, created_at, updated_at)
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            """,
            (doctor_id, "模拟测试医生", "心血管内科"),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SOAP snapshot helper
# ---------------------------------------------------------------------------

_SOAP_FIELDS = [
    "chief_complaint", "present_illness", "past_history",
    "allergy_history", "family_history", "personal_history",
    "marital_reproductive", "physical_exam", "specialist_exam",
    "auxiliary_exam", "diagnosis", "treatment_plan", "orders_followup",
]


def _snapshot_soap(db_path: str, record_id: int) -> dict:
    """Read SOAP fields from medical_records."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cols = ", ".join(_SOAP_FIELDS)
        row = conn.execute(
            f"SELECT {cols} FROM medical_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        conn.close()
        if row:
            return {f: (row[f] or "") for f in _SOAP_FIELDS}
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

async def run_persona(
    persona: dict,
    server_url: str,
    db_path: str,
) -> dict:
    """Run a single doctor persona end-to-end through the doctor interview API.

    Parameters
    ----------
    persona:
        Persona definition dict.  Must include at minimum:
        ``id``, ``name``, ``style``, ``turn_plan``, ``fact_catalog``.
        turn_plan is a list of dicts with ``turn`` (int) and ``text`` (str).
    server_url:
        Base URL of the running server (e.g. ``http://127.0.0.1:8000``).
    db_path:
        Path to the SQLite database file.

    Returns
    -------
    dict
        Results with keys: ``persona_id``, ``turns``, ``session_id``,
        ``record_id``, ``soap_snapshot``, ``confirm_data``, ``turn_responses``.
    """

    persona_id: str = persona["id"]
    doctor_id = f"docsim_{persona_id}_{uuid4().hex[:6]}"

    # Patient info from persona (or defaults)
    pi = persona.get("patient_info", {})
    patient_name = pi.get("name", persona.get("patient_name", "模拟患者"))
    patient_gender = pi.get("gender", persona.get("patient_gender", "男"))
    patient_age = pi.get("age", persona.get("patient_age", 60))

    # 1. Ensure test doctor exists
    _ensure_doctor(db_path, doctor_id)

    server = server_url.rstrip("/")
    turn_plan = persona.get("turn_plan", [])

    session_id: Optional[str] = None
    turn_responses: list[dict] = []

    async with httpx.AsyncClient(timeout=60.0) as http:

        # ------------------------------------------------------------------
        # 2. Send each scripted turn
        # ------------------------------------------------------------------
        for step in turn_plan:
            text = step["text"]

            form_data = {
                "text": text,
                "doctor_id": doctor_id,
            }

            if session_id is None:
                # First turn — include patient info
                form_data["patient_name"] = patient_name
                form_data["patient_gender"] = patient_gender
                form_data["patient_age"] = str(patient_age)
            else:
                form_data["session_id"] = session_id

            resp = await http.post(
                f"{server}/api/records/interview/turn",
                data=form_data,
            )
            resp.raise_for_status()
            data = resp.json()

            # Capture session_id from first turn
            if session_id is None:
                session_id = data["session_id"]

            turn_responses.append({
                "turn": step.get("turn", len(turn_responses) + 1),
                "input_text": text,
                "reply": data.get("reply", ""),
                "collected": data.get("collected", {}),
                "progress": data.get("progress", {}),
                "status": data.get("status", ""),
                "missing": data.get("missing", []),
            })

        # ------------------------------------------------------------------
        # 3. Confirm interview
        # ------------------------------------------------------------------
        confirm_resp = await http.post(
            f"{server}/api/records/interview/confirm",
            data={
                "session_id": session_id,
                "doctor_id": doctor_id,
            },
        )
        confirm_resp.raise_for_status()
        confirm_data = confirm_resp.json()

    # ------------------------------------------------------------------
    # 4. Snapshot SOAP fields from DB
    # ------------------------------------------------------------------
    record_id_str = confirm_data.get("pending_id")
    record_id = int(record_id_str) if record_id_str else None
    soap_snapshot = {}
    if record_id:
        soap_snapshot = _snapshot_soap(db_path, record_id)

    # ------------------------------------------------------------------
    # 5. Build results
    # ------------------------------------------------------------------
    return {
        "persona_id": persona_id,
        "persona": persona,
        "doctor_id": doctor_id,
        "turns": len(turn_plan),
        "session_id": session_id,
        "record_id": record_id,
        "soap_snapshot": soap_snapshot,
        "confirm_data": confirm_data,
        "turn_responses": turn_responses,
    }


def cleanup_sim_data(db_path: str) -> int:
    """Delete all rows with doctor_id LIKE 'docsim_%'. Returns count deleted."""
    tables = [
        "doctor_tasks", "medical_records", "interview_sessions",
        "patients", "doctor_contexts", "doctor_conversation_turns",
        "chat_archive", "doctors",
    ]
    total = 0
    conn = sqlite3.connect(db_path)
    try:
        for table in tables:
            try:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE doctor_id LIKE 'docsim_%'"  # noqa: S608
                )
                total += cur.rowcount
            except sqlite3.OperationalError:
                pass  # table may not exist
        conn.commit()
    finally:
        conn.close()
    return total
