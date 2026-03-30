"""Reply simulation engine — seeds DB, sends patient message via /chat, collects response."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ensure_doctor(db_path: str, doctor_id: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO doctors (doctor_id, name, specialty, created_at, updated_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (doctor_id, "回复模拟测试医生", "神经外科"),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_patient(db_path: str, doctor_id: str, patient: dict) -> int:
    """Insert test patient row, return patient_id."""
    year_of_birth = 2026 - patient.get("age", 50)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO patients (doctor_id, name, gender, year_of_birth, phone, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (doctor_id, patient.get("name", "测试患者"),
             patient.get("gender", "男"), year_of_birth,
             f"138{uuid4().hex[:8]}"),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _seed_medical_record(db_path: str, doctor_id: str, patient_id: int, record: dict) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO medical_records "
            "(doctor_id, patient_id, record_type, status, "
            " chief_complaint, diagnosis, treatment_plan, orders_followup, "
            " content, created_at, updated_at) "
            "VALUES (?, ?, 'visit', 'completed', ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (doctor_id, patient_id,
             record.get("chief_complaint", ""),
             record.get("diagnosis", ""),
             record.get("treatment_plan", ""),
             record.get("orders_followup", ""),
             record.get("chief_complaint", "")),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _seed_knowledge_items(db_path: str, doctor_id: str, items: List[dict]) -> List[int]:
    if not items:
        return []
    conn = sqlite3.connect(db_path)
    ids = []
    try:
        for item in items:
            cursor = conn.execute(
                "INSERT INTO doctor_knowledge_items "
                "(doctor_id, content, category, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
                (doctor_id, item.get("content", ""),
                 item.get("category", "custom"), item.get("title", "")),
            )
            ids.append(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return ids


def _get_patient_token(db_path: str, patient_id: int) -> Optional[str]:
    """Generate a JWT token for the patient by calling the auth endpoint."""
    return None  # Will use direct API with patient registration


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_sim_data(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    total = 0
    try:
        for table in ["message_drafts", "patient_messages", "ai_suggestions",
                       "doctor_knowledge_items", "medical_records", "patients", "doctors"]:
            try:
                col = "doctor_id"
                if table == "patients":
                    col = "doctor_id"
                cursor = conn.execute(f"DELETE FROM {table} WHERE {col} LIKE 'rxsim_%'")
                total += cursor.rowcount
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()
    return total


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

async def run_scenario(
    scenario: Dict[str, Any],
    server_url: str,
    db_path: str,
) -> Dict[str, Any]:
    """Run a single reply scenario end-to-end.

    1. Seed doctor, patient, record, KB
    2. Register patient via API (get JWT)
    3. Send message via POST /chat
    4. Return response for validation
    """
    scenario_id = scenario["id"]
    doctor_id = f"rxsim_{scenario_id}_{uuid4().hex[:6]}"
    server = server_url.rstrip("/")

    # Seed doctor + KB first (patient created via API registration)
    _ensure_doctor(db_path, doctor_id)

    kb_items_raw = scenario.get("knowledge_items", [])
    kb_ids = _seed_knowledge_items(db_path, doctor_id, kb_items_raw)

    kb_relevant_ids = [kb_ids[i] for i, item in enumerate(kb_items_raw)
                       if i < len(kb_ids) and item.get("relevant", True)]
    kb_irrelevant_ids = [kb_ids[i] for i, item in enumerate(kb_items_raw)
                         if i < len(kb_ids) and not item.get("relevant", True)]

    patient_info = scenario.get("patient", {})
    record = scenario.get("record", {})
    phone = f"138{uuid4().hex[:8]}"

    result = {
        "scenario_id": scenario_id,
        "doctor_id": doctor_id,
        "patient_id": None,
        "record_id": None,
        "kb_ids": kb_ids,
        "kb_relevant_ids": kb_relevant_ids,
        "kb_irrelevant_ids": kb_irrelevant_ids,
        "kb_items_meta": kb_items_raw,
        "message": scenario.get("message", ""),
        "reply": "",
        "triage_category": "",
        "ai_handled": None,
        "error": None,
        "response_time_s": 0,
    }

    async with httpx.AsyncClient(timeout=60.0) as http:
        # Register patient via API → get JWT + patient_id
        try:
            reg_resp = await http.post(
                f"{server}/api/auth/unified/register/patient",
                json={
                    "doctor_id": doctor_id,
                    "name": patient_info.get("name", "测试患者"),
                    "phone": phone,
                    "gender": patient_info.get("gender", "男"),
                    "year_of_birth": 2026 - patient_info.get("age", 50),
                },
            )
            if reg_resp.status_code != 200:
                result["error"] = f"Register failed: {reg_resp.status_code} {reg_resp.text[:200]}"
                return result
            token = reg_resp.json().get("token", "")
            patient_id = reg_resp.json().get("patient_id")
            result["patient_id"] = patient_id
        except Exception as exc:
            result["error"] = f"Register error: {exc}"
            return result

        # Seed medical record linked to this patient
        record_id = _seed_medical_record(db_path, doctor_id, patient_id, record)
        result["record_id"] = record_id

        # Send message via /chat
        start = time.monotonic()
        try:
            chat_resp = await http.post(
                f"{server}/api/patient/chat",
                json={"text": scenario["message"]},
                headers={"Authorization": f"Bearer {token}"},
            )
            result["response_time_s"] = round(time.monotonic() - start, 1)

            if chat_resp.status_code != 200:
                result["error"] = f"Chat failed: {chat_resp.status_code} {chat_resp.text[:200]}"
                return result

            data = chat_resp.json()
            result["reply"] = data.get("reply", "")
            result["triage_category"] = data.get("triage_category", "")
            result["ai_handled"] = data.get("ai_handled")
        except Exception as exc:
            result["error"] = f"Chat error: {exc}"
            result["response_time_s"] = round(time.monotonic() - start, 1)

    return result
