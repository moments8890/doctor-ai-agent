"""Chat simulation engine — seeds DB, sends doctor messages via /api/records/chat."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List
from uuid import uuid4

import httpx


def _ensure_doctor(db_path: str, doctor_id: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO doctors (doctor_id, name, specialty, created_at, updated_at) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            (doctor_id, "聊天模拟测试医生", "神经外科"),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_patient(db_path: str, doctor_id: str, patient: dict) -> int:
    conn = sqlite3.connect(db_path)
    try:
        name = patient.get("name", "测试患者")
        cursor = conn.execute(
            "INSERT INTO patients (doctor_id, name, gender, year_of_birth, phone, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (doctor_id, name, patient.get("gender", "男"), 1970, f"138{uuid4().hex[:8]}"),
        )
        patient_id = cursor.lastrowid

        rec = patient.get("record", {})
        if rec:
            conn.execute(
                "INSERT INTO medical_records "
                "(doctor_id, patient_id, record_type, status, chief_complaint, diagnosis, "
                " treatment_plan, orders_followup, content, created_at, updated_at) "
                "VALUES (?, ?, 'visit', 'completed', ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (doctor_id, patient_id,
                 rec.get("chief_complaint", ""),
                 rec.get("diagnosis", ""),
                 rec.get("treatment_plan", ""),
                 rec.get("orders_followup", ""),
                 rec.get("chief_complaint", "")),
            )
        conn.commit()
        return patient_id
    finally:
        conn.close()


def _seed_tasks(db_path: str, doctor_id: str, tasks: List[dict]) -> List[int]:
    if not tasks:
        return []
    conn = sqlite3.connect(db_path)
    ids = []
    try:
        for t in tasks:
            cursor = conn.execute(
                "INSERT INTO doctor_tasks "
                "(doctor_id, task_type, title, status, due_at, created_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', datetime('now', '+1 day'), datetime('now'), datetime('now'))",
                (doctor_id, t.get("task_type", "general"), t.get("title", "")),
            )
            ids.append(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return ids


def cleanup_sim_data(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    total = 0
    try:
        for table in ["doctor_tasks", "medical_records", "patients",
                       "doctor_chat_log", "doctors"]:
            try:
                cursor = conn.execute(f"DELETE FROM {table} WHERE doctor_id LIKE 'cxsim_%'")
                total += cursor.rowcount
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()
    return total


async def run_scenario(
    scenario: Dict[str, Any],
    server_url: str,
    db_path: str,
) -> Dict[str, Any]:
    scenario_id = scenario["id"]
    doctor_id = f"cxsim_{scenario_id}_{uuid4().hex[:6]}"
    server = server_url.rstrip("/")

    _ensure_doctor(db_path, doctor_id)

    for p in scenario.get("seed_patients", []):
        _seed_patient(db_path, doctor_id, p)
    task_ids = _seed_tasks(db_path, doctor_id, scenario.get("seed_tasks", []))

    result = {
        "scenario_id": scenario_id,
        "doctor_id": doctor_id,
        "message": scenario.get("message", ""),
        "reply": "",
        "intent": "",
        "view_payload": None,
        "error": None,
        "response_time_s": 0,
    }

    import time
    async with httpx.AsyncClient(timeout=60.0) as http:
        start = time.monotonic()
        try:
            resp = await http.post(
                f"{server}/api/records/chat",
                json={"text": scenario["message"], "doctor_id": doctor_id},
            )
            result["response_time_s"] = round(time.monotonic() - start, 1)

            if resp.status_code != 200:
                result["error"] = f"Chat failed: {resp.status_code} {resp.text[:200]}"
                return result

            data = resp.json()
            result["reply"] = data.get("reply", "")
            result["view_payload"] = data.get("view_payload", {})
            routing = (data.get("view_payload") or {}).get("_routing", {})
            result["intent"] = routing.get("intent", "")
        except Exception as exc:
            result["error"] = f"Chat error: {exc}"
            result["response_time_s"] = round(time.monotonic() - start, 1)

    return result
