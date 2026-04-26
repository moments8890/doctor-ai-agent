"""Simulation engine — runs one persona through the patient intake pipeline."""
from __future__ import annotations

import sqlite3
from typing import Optional
from uuid import uuid4

import httpx

from .patient_llm import generate_patient_response


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
            (doctor_id, "模拟测试医生", "神经外科"),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

async def run_persona(
    persona: dict,
    server_url: str,
    patient_llm_provider: str,
    db_path: str,
) -> dict:
    """Run a single persona end-to-end through the patient intake API.

    Parameters
    ----------
    persona:
        Persona definition dict.  Must include at minimum:
        ``id``, ``name``, ``age``, ``gender``, ``year_of_birth``, ``phone``,
        ``background``, ``medications``, ``surgical_history``,
        ``allowed_facts``, ``personality``.
    server_url:
        Base URL of the running server (e.g. ``http://127.0.0.1:8000``).
    patient_llm_provider:
        LLM provider for patient responses (``groq``, ``deepseek``, ``claude``).
    db_path:
        Path to the SQLite database file.

    Returns
    -------
    dict
        Results with keys: ``persona_id``, ``turns``, ``session_id``,
        ``record_id``, ``review_id``, ``conversation``, ``collected``,
        ``structured``.
    """

    persona_id: str = persona["id"]
    doctor_id = f"intsim_{persona_id}_{uuid4().hex[:6]}"

    # 1. Ensure test doctor exists
    _ensure_doctor(db_path, doctor_id)

    server = server_url.rstrip("/")

    async with httpx.AsyncClient(timeout=60.0) as http:

        # ------------------------------------------------------------------
        # 2. Register patient via unified auth (issues token with role claim)
        # ------------------------------------------------------------------
        reg_resp = await http.post(
            f"{server}/api/auth/unified/register/patient",
            json={
                "doctor_id": doctor_id,
                "name": persona["name"],
                "gender": persona.get("gender"),
                "year_of_birth": persona["year_of_birth"],
                "phone": persona["phone"],
            },
        )
        reg_resp.raise_for_status()
        reg_data = reg_resp.json()
        token: str = reg_data["token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # ------------------------------------------------------------------
        # 4. Start intake
        # ------------------------------------------------------------------
        start_resp = await http.post(
            f"{server}/api/patient/intake/start",
            headers=auth_headers,
        )
        start_resp.raise_for_status()
        start_data = start_resp.json()

        session_id: str = start_data["session_id"]
        system_reply: str = start_data["reply"]
        collected: dict = start_data.get("collected", {})
        progress: dict = start_data.get("progress", {"filled": 0, "total": 0})
        status: str = start_data.get("status", "active")

        # Track the full conversation for the result
        conversation: list[dict] = [
            {"role": "system", "text": system_reply},
        ]

        # ------------------------------------------------------------------
        # 5. Intake loop
        # ------------------------------------------------------------------
        # Stress-test personas get higher turn limits
        max_turns = 50 if persona_id.startswith("STRESS") else 20
        turn_count = 0

        complete = False

        for turn_idx in range(max_turns):
            # --- Stop conditions: respect the system's own completeness ---
            if complete:
                break
            if status != "active":
                break

            # --- Generate patient response ---
            patient_text = await generate_patient_response(
                persona=persona,
                conversation=conversation,
                system_message=system_reply,
                provider=patient_llm_provider,
            )
            conversation.append({"role": "patient", "text": patient_text})
            turn_count += 1

            # --- Send turn to server ---
            turn_resp = await http.post(
                f"{server}/api/patient/intake/turn",
                headers=auth_headers,
                json={
                    "session_id": session_id,
                    "text": patient_text,
                },
            )
            turn_resp.raise_for_status()
            turn_data = turn_resp.json()

            system_reply = turn_data.get("reply", "")
            collected = turn_data.get("collected", collected)
            progress = turn_data.get("progress", progress)
            status = turn_data.get("status", status)
            complete = turn_data.get("complete", False)
            suggestions = turn_data.get("suggestions", [])

            # Append suggestions to system reply so the simulated patient
            # can see the follow-up prompts (like a real patient seeing chips)
            if suggestions:
                system_reply += "\n（快捷回复：" + "、".join(suggestions) + "）"

            conversation.append({"role": "system", "text": system_reply})

        # ------------------------------------------------------------------
        # 6. Confirm intake
        # ------------------------------------------------------------------
        confirm_resp = await http.post(
            f"{server}/api/patient/intake/confirm",
            headers=auth_headers,
            json={"session_id": session_id},
        )
        confirm_resp.raise_for_status()
        confirm_data = confirm_resp.json()

    # ------------------------------------------------------------------
    # 7. Snapshot clinical record fields from DB (before cleanup deletes them)
    # ------------------------------------------------------------------
    record_id = confirm_data.get("record_id")
    structured_snapshot = {}
    if record_id:
        try:
            from patient_sim.validator import CLINICAL_FIELDS
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    f"SELECT {', '.join(CLINICAL_FIELDS)} FROM medical_records WHERE id = ?",
                    (record_id,),
                ).fetchone()
                if row:
                    structured_snapshot = {f: (row[f] or "") for f in CLINICAL_FIELDS}
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 8. Build results
    # ------------------------------------------------------------------
    return {
        "persona_id": persona_id,
        "persona": persona,
        "doctor_id": doctor_id,
        "turns": turn_count,
        "session_id": session_id,
        "record_id": record_id,
        "review_id": confirm_data.get("review_id"),
        "structured_snapshot": structured_snapshot,
        "conversation": conversation,
        "collected": collected,
        "structured": confirm_data,
    }


def cleanup_sim_data(db_path: str) -> int:
    """Delete all rows with doctor_id LIKE 'intsim_%'. Returns count deleted."""
    tables = [
        "doctor_tasks", "medical_records", "intake_sessions",
        "patients", "doctor_contexts", "doctor_conversation_turns",
        "chat_archive", "doctors",
    ]
    total = 0
    conn = sqlite3.connect(db_path)
    try:
        for table in tables:
            try:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE doctor_id LIKE 'intsim_%'"  # noqa: S608
                )
                total += cur.rowcount
            except sqlite3.OperationalError:
                pass  # table may not exist
        conn.commit()
    finally:
        conn.close()
    return total
