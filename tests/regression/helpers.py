from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import httpx

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

CLINICAL_FIELDS = [
    "chief_complaint", "present_illness", "past_history", "allergy_history",
    "personal_history", "marital_reproductive", "family_history",
    "physical_exam", "specialist_exam", "auxiliary_exam",
    "diagnosis", "treatment_plan", "orders_followup",
]

# --- API wrappers ---


def intake_turn(
    server_url: str,
    text: str,
    session_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
) -> dict:
    """POST /api/records/intake/turn (form-encoded). Returns response JSON. Raises on non-2xx."""
    data = {"text": text}
    if session_id:
        data["session_id"] = session_id
    if doctor_id:
        data["doctor_id"] = doctor_id
    resp = httpx.post(
        f"{server_url}/api/records/intake/turn", data=data, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def intake_confirm(
    server_url: str, session_id: str, doctor_id: str
) -> Tuple[int, dict]:
    """POST /api/records/intake/confirm (form-encoded). Returns (status_code, body). Does NOT raise."""
    data = {"session_id": session_id, "doctor_id": doctor_id}
    resp = httpx.post(
        f"{server_url}/api/records/intake/confirm", data=data, timeout=_TIMEOUT
    )
    try:
        body = resp.json()
    except Exception:
        body = {}
    return resp.status_code, body


def intake_cancel(server_url: str, session_id: str, doctor_id: str) -> dict:
    """POST /api/records/intake/cancel (form-encoded). Raises on non-2xx."""
    data = {"session_id": session_id, "doctor_id": doctor_id}
    resp = httpx.post(
        f"{server_url}/api/records/intake/cancel", data=data, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def get_session(server_url: str, session_id: str, doctor_id: str) -> dict:
    """GET /api/records/intake/session/{session_id}. Returns response JSON."""
    resp = httpx.get(
        f"{server_url}/api/records/intake/session/{session_id}",
        params={"doctor_id": doctor_id},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def carry_forward_confirm(
    server_url: str,
    session_id: str,
    doctor_id: str,
    field_name: str,
    action: str = "confirm",
) -> dict:
    """POST /api/records/intake/carry-forward-confirm (JSON body)."""
    payload = {
        "session_id": session_id,
        "doctor_id": doctor_id,
        "field": field_name,
        "action": action,
    }
    resp = httpx.post(
        f"{server_url}/api/records/intake/carry-forward-confirm",
        json=payload,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def chat(server_url: str, text: str, doctor_id: str) -> dict:
    """POST /api/records/chat (JSON body). Raises on non-2xx."""
    payload = {"text": text, "doctor_id": doctor_id, "history": []}
    resp = httpx.post(
        f"{server_url}/api/records/chat", json=payload, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


# --- DB helpers ---


def db_count(db_path: str, doctor_id: str, table: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE doctor_id = ?", (doctor_id,)
        ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def db_patient(
    db_path: str, doctor_id: str, name: str
) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM patients WHERE doctor_id = ? AND name = ? ORDER BY id DESC LIMIT 1",
            (doctor_id, name),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def db_record_fields(db_path: str, doctor_id: str) -> Dict[str, str]:
    """Get the 13 clinical fields from the latest medical record for this doctor."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM medical_records WHERE doctor_id = ? ORDER BY id DESC LIMIT 1",
            (doctor_id,),
        ).fetchone()
        if not row:
            return {}
        result = {}
        for f in CLINICAL_FIELDS:
            val = row[f] if f in row.keys() else None
            if val:
                result[f] = str(val)
        return result
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def db_session_status(db_path: str, session_id: str) -> Optional[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT status FROM intake_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def db_task_count(db_path: str, doctor_id: str) -> int:
    return db_count(db_path, doctor_id, "doctor_tasks")
