"""Simulation engine — runs one doctor persona through the doctor intake pipeline.

Doctor personas use either:
  - scripted ``turn_plan`` (styles: verbose, multi_turn, template_fill, etc.)
  - LLM-generated turns (style: ``interactive``) via ``doctor_llm``

Each turn is sent as Form data to POST /api/records/intake/turn.
After all turns, calls POST /api/records/intake/confirm.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional
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
# 病历字段 snapshot helper
# ---------------------------------------------------------------------------

from patient_sim.validator import CLINICAL_FIELDS as _RECORD_FIELDS


def _snapshot_record(db_path: str, record_id: int) -> dict:
    """Read clinical record fields from medical_records."""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cols = ", ".join(_RECORD_FIELDS)
            row = conn.execute(
                f"SELECT {cols} FROM medical_records WHERE id = ?",
                (record_id,),
            ).fetchone()
            if row:
                return {f: (row[f] or "") for f in _RECORD_FIELDS}
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Scripted turn runner
# ---------------------------------------------------------------------------

async def _run_scripted_turns(
    http: httpx.AsyncClient,
    server: str,
    turn_plan: list,
    doctor_id: str,
    patient_name: str,
    patient_gender: str,
    patient_age: int,
) -> tuple:
    """Execute scripted turn_plan turns.  Returns (session_id, turn_responses)."""
    session_id: Optional[str] = None
    turn_responses: List[dict] = []

    for step in turn_plan:
        text = step["text"]

        form_data = {
            "text": text,
            "doctor_id": doctor_id,
        }

        if session_id is None:
            form_data["patient_name"] = patient_name
            form_data["patient_gender"] = patient_gender
            form_data["patient_age"] = str(patient_age)
        else:
            form_data["session_id"] = session_id

        resp = await http.post(
            f"{server}/api/records/intake/turn",
            data=form_data,
        )
        resp.raise_for_status()
        data = resp.json()

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

    return session_id, turn_responses


# ---------------------------------------------------------------------------
# Interactive (LLM-driven) turn runner
# ---------------------------------------------------------------------------

async def _run_interactive_turns(
    http: httpx.AsyncClient,
    server: str,
    persona: dict,
    doctor_id: str,
    patient_name: str,
    patient_gender: str,
    patient_age: int,
) -> tuple:
    """Execute LLM-generated doctor turns.  Returns (session_id, turn_responses).

    The doctor LLM reads the agent's response after each turn and decides
    what to enter next.  Stops when:
      - the agent reports no missing required fields, OR
      - ``max_turns`` is reached
    """
    from doctor_sim.doctor_llm import generate_doctor_input

    clinical_case: str = persona["clinical_case"]
    max_turns: int = persona.get("max_turns", 5)
    patient_info = persona.get("patient_info", {})

    session_id: Optional[str] = None
    turn_responses: List[dict] = []
    previous_inputs: List[str] = []
    dynamic_turn_plan: List[dict] = []  # backfill for validator

    for turn_num in range(1, max_turns + 1):
        # Determine context from previous agent response
        if turn_responses:
            last = turn_responses[-1]
            collected = last.get("collected", {})
            missing = last.get("missing", [])
            suggestions = last.get("reply", "")
        else:
            collected = None
            missing = None
            suggestions = None

        # --- Generate doctor input via LLM ---
        text = await generate_doctor_input(
            clinical_case=clinical_case,
            collected=collected,
            missing=missing,
            suggestions=suggestions,
            previous_inputs=previous_inputs,
            is_first_turn=(turn_num == 1),
            patient_info=patient_info,
        )

        # If the LLM says "确认生成", we're done entering — go to confirm
        if "确认生成" in text and len(text) < 20:
            break

        previous_inputs.append(text)
        dynamic_turn_plan.append({"turn": turn_num, "text": text})

        # --- Send to the intake API ---
        form_data = {
            "text": text,
            "doctor_id": doctor_id,
        }

        if session_id is None:
            form_data["patient_name"] = patient_name
            form_data["patient_gender"] = patient_gender
            form_data["patient_age"] = str(patient_age)
        else:
            form_data["session_id"] = session_id

        resp = await http.post(
            f"{server}/api/records/intake/turn",
            data=form_data,
        )
        resp.raise_for_status()
        data = resp.json()

        if session_id is None:
            session_id = data["session_id"]

        turn_resp = {
            "turn": turn_num,
            "input_text": text,
            "reply": data.get("reply", ""),
            "collected": data.get("collected", {}),
            "progress": data.get("progress", {}),
            "status": data.get("status", ""),
            "missing": data.get("missing", []),
        }
        turn_responses.append(turn_resp)

        # If no missing fields, stop early
        if not data.get("missing"):
            break

    # Backfill turn_plan on persona so the validator can build doctor_input_text
    persona["turn_plan"] = dynamic_turn_plan

    return session_id, turn_responses


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

async def run_persona(
    persona: dict,
    server_url: str,
    db_path: str,
) -> dict:
    """Run a single doctor persona end-to-end through the doctor intake API.

    Parameters
    ----------
    persona:
        Persona definition dict.  Must include at minimum:
        ``id``, ``name``, ``style``.
        For scripted personas: ``turn_plan`` (list of {turn, text}).
        For interactive personas: ``clinical_case`` (str), ``max_turns`` (int).
    server_url:
        Base URL of the running server (e.g. ``http://127.0.0.1:8000``).
    db_path:
        Path to the SQLite database file.

    Returns
    -------
    dict
        Results with keys: ``persona_id``, ``turns``, ``session_id``,
        ``record_id``, ``structured_snapshot``, ``confirm_data``, ``turn_responses``.
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
    is_interactive = persona.get("style") == "interactive"

    session_id: Optional[str] = None
    turn_responses: List[dict] = []

    async with httpx.AsyncClient(timeout=60.0) as http:

        # ------------------------------------------------------------------
        # 2. Run turns (scripted or interactive)
        # ------------------------------------------------------------------
        if is_interactive:
            session_id, turn_responses = await _run_interactive_turns(
                http, server, persona, doctor_id,
                patient_name, patient_gender, patient_age,
            )
        else:
            turn_plan = persona.get("turn_plan", [])
            session_id, turn_responses = await _run_scripted_turns(
                http, server, turn_plan, doctor_id,
                patient_name, patient_gender, patient_age,
            )

        # ------------------------------------------------------------------
        # 3. Confirm intake
        # ------------------------------------------------------------------
        confirm_resp = await http.post(
            f"{server}/api/records/intake/confirm",
            data={
                "session_id": session_id,
                "doctor_id": doctor_id,
            },
        )
        confirm_resp.raise_for_status()
        confirm_data = confirm_resp.json()

    # ------------------------------------------------------------------
    # 4. Snapshot clinical record fields from DB
    # ------------------------------------------------------------------
    record_id_str = confirm_data.get("pending_id")
    record_id = int(record_id_str) if record_id_str else None
    structured_snapshot = {}
    if record_id:
        structured_snapshot = _snapshot_record(db_path, record_id)

    # ------------------------------------------------------------------
    # 5. Build results
    # ------------------------------------------------------------------
    return {
        "persona_id": persona_id,
        "persona": persona,
        "doctor_id": doctor_id,
        "turns": len(turn_responses),
        "session_id": session_id,
        "record_id": record_id,
        "structured_snapshot": structured_snapshot,
        "confirm_data": confirm_data,
        "turn_responses": turn_responses,
    }


def cleanup_sim_data(db_path: str) -> int:
    """Delete all rows with doctor_id LIKE 'docsim_%'. Returns count deleted."""
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
                    f"DELETE FROM {table} WHERE doctor_id LIKE 'docsim_%'"  # noqa: S608
                )
                total += cur.rowcount
            except sqlite3.OperationalError:
                pass  # table may not exist
        conn.commit()
    finally:
        conn.close()
    return total
