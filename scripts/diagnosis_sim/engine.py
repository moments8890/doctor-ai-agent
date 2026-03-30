"""Diagnosis simulation engine — seeds DB, triggers diagnosis, collects results."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx


# ---------------------------------------------------------------------------
# DB helpers — direct SQLite for seeding (same pattern as patient_sim)
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
            (doctor_id, "诊断模拟测试医生", "神经外科"),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_medical_record(
    db_path: str,
    doctor_id: str,
    record_fields: Dict[str, str],
) -> int:
    """Insert a medical record with structured fields. Returns record_id."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO medical_records
                (doctor_id, record_type, status,
                 department, chief_complaint, present_illness,
                 past_history, allergy_history, personal_history,
                 marital_reproductive, family_history,
                 physical_exam, specialist_exam, auxiliary_exam,
                 diagnosis, treatment_plan, orders_followup,
                 content, created_at, updated_at)
            VALUES (?, 'visit', 'pending_review',
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, datetime('now'), datetime('now'))
            """,
            (
                doctor_id,
                record_fields.get("department", ""),
                record_fields.get("chief_complaint", ""),
                record_fields.get("present_illness", ""),
                record_fields.get("past_history", ""),
                record_fields.get("allergy_history", ""),
                record_fields.get("personal_history", ""),
                record_fields.get("marital_reproductive", ""),
                record_fields.get("family_history", ""),
                record_fields.get("physical_exam", ""),
                record_fields.get("specialist_exam", ""),
                record_fields.get("auxiliary_exam", ""),
                record_fields.get("diagnosis", ""),
                record_fields.get("treatment_plan", ""),
                record_fields.get("orders_followup", ""),
                record_fields.get("chief_complaint", ""),  # content = CC for display
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _seed_knowledge_items(
    db_path: str,
    doctor_id: str,
    items: List[Dict[str, Any]],
) -> List[int]:
    """Insert knowledge items for the doctor. Returns list of KB IDs."""
    if not items:
        return []
    conn = sqlite3.connect(db_path)
    ids = []
    try:
        for item in items:
            cursor = conn.execute(
                """
                INSERT INTO doctor_knowledge_items
                    (doctor_id, content, category, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    doctor_id,
                    item.get("content", ""),
                    item.get("category", "custom"),
                    item.get("title", ""),
                ),
            )
            ids.append(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()
    return ids


def _seed_prior_cases(
    db_path: str,
    doctor_id: str,
    cases: List[Dict[str, Any]],
) -> List[int]:
    """Seed prior confirmed cases (records + confirmed suggestions)."""
    if not cases:
        return []
    conn = sqlite3.connect(db_path)
    record_ids = []
    try:
        for case in cases:
            rec = case.get("record", {})
            cursor = conn.execute(
                """
                INSERT INTO medical_records
                    (doctor_id, record_type, status,
                     chief_complaint, present_illness, past_history,
                     auxiliary_exam, content, created_at, updated_at)
                VALUES (?, 'visit', 'completed',
                        ?, ?, ?,
                        ?, ?, datetime('now', '-30 days'), datetime('now', '-30 days'))
                """,
                (
                    doctor_id,
                    rec.get("chief_complaint", ""),
                    rec.get("present_illness", ""),
                    rec.get("past_history", ""),
                    rec.get("auxiliary_exam", ""),
                    rec.get("chief_complaint", ""),
                ),
            )
            case_record_id = cursor.lastrowid
            record_ids.append(case_record_id)

            # Seed confirmed suggestions for this case
            for sug in case.get("suggestions", []):
                conn.execute(
                    """
                    INSERT INTO ai_suggestions
                        (record_id, doctor_id, section, content, detail,
                         confidence, urgency, intervention, decision,
                         decided_at, is_custom, created_at)
                    VALUES (?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            datetime('now', '-30 days'), 0, datetime('now', '-30 days'))
                    """,
                    (
                        case_record_id,
                        doctor_id,
                        sug.get("section", "differential"),
                        sug.get("content", ""),
                        sug.get("detail", ""),
                        sug.get("confidence"),
                        sug.get("urgency"),
                        sug.get("intervention"),
                        sug.get("decision", "confirmed"),
                    ),
                )
        conn.commit()
    finally:
        conn.close()
    return record_ids


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_sim_data(db_path: str) -> int:
    """Delete all rows created by diagnosis sim (doctor_id LIKE 'dxsim_%')."""
    conn = sqlite3.connect(db_path)
    total = 0
    try:
        for table in [
            "ai_suggestions",
            "doctor_knowledge_items",
            "medical_records",
            "doctors",
        ]:
            try:
                col = "doctor_id"
                cursor = conn.execute(
                    f"DELETE FROM {table} WHERE {col} LIKE 'dxsim_%'"
                )
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

async def _run_single(
    scenario_id: str,
    doctor_id: str,
    record_fields: Dict[str, str],
    kb_items_raw: List[Dict[str, Any]],
    prior_cases: List[Dict[str, Any]],
    server_url: str,
    db_path: str,
    poll_timeout: float = 90.0,
    poll_interval: float = 2.0,
) -> Dict[str, Any]:
    """Run a single diagnosis pass: seed → trigger → poll → return suggestions."""
    server = server_url.rstrip("/")

    _ensure_doctor(db_path, doctor_id)
    record_id = _seed_medical_record(db_path, doctor_id, record_fields)
    kb_ids = _seed_knowledge_items(db_path, doctor_id, kb_items_raw)
    case_record_ids = _seed_prior_cases(db_path, doctor_id, prior_cases)

    result = {
        "doctor_id": doctor_id,
        "record_id": record_id,
        "kb_ids": kb_ids,
        "case_record_ids": case_record_ids,
        "suggestions": [],
        "error": None,
        "diagnosis_time_s": 0,
    }

    async with httpx.AsyncClient(timeout=90.0) as http:
        try:
            resp = await http.post(
                f"{server}/api/doctor/records/{record_id}/diagnose",
                json={"doctor_id": doctor_id},
            )
            if resp.status_code not in (200, 202):
                result["error"] = f"Diagnose trigger failed: {resp.status_code} {resp.text[:200]}"
                return result
        except Exception as exc:
            result["error"] = f"Diagnose trigger error: {exc}"
            return result

        start = time.monotonic()
        suggestions = []
        while time.monotonic() - start < poll_timeout:
            await asyncio.sleep(poll_interval)
            try:
                resp = await http.get(
                    f"{server}/api/doctor/records/{record_id}/suggestions",
                    params={"doctor_id": doctor_id},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    suggestions = data.get("suggestions", [])
                    if suggestions:
                        break
            except Exception:
                pass

        result["diagnosis_time_s"] = round(time.monotonic() - start, 1)
        result["suggestions"] = suggestions
        if not suggestions:
            result["error"] = f"No suggestions after {poll_timeout}s polling"

    return result


async def run_scenario(
    scenario: Dict[str, Any],
    server_url: str,
    db_path: str,
    poll_timeout: float = 90.0,
    poll_interval: float = 2.0,
) -> Dict[str, Any]:
    """Run a single diagnosis scenario end-to-end.

    Runs TWO passes when KB or cases are injected:
    1. Baseline: same record, NO KB, NO cases → proves what LLM knows without injection
    2. Full: record + KB + cases → proves injection changes the output

    Returns results with both passes for counterfactual comparison.
    """
    scenario_id = scenario["id"]
    record_fields = scenario.get("record", {})
    kb_items_raw = scenario.get("knowledge_items", [])
    prior_cases = scenario.get("prior_cases", [])
    has_injection = bool(kb_items_raw) or bool(prior_cases)

    # --- Baseline run (no KB, no cases) — only when injection exists ---
    baseline_suggestions = []
    if has_injection:
        baseline_id = f"dxsim_{scenario_id}_base_{uuid4().hex[:4]}"
        baseline = await _run_single(
            scenario_id, baseline_id, record_fields,
            kb_items_raw=[], prior_cases=[],
            server_url=server_url, db_path=db_path,
            poll_timeout=poll_timeout, poll_interval=poll_interval,
        )
        baseline_suggestions = baseline.get("suggestions", [])

    # --- Full run (with KB + cases) ---
    full_id = f"dxsim_{scenario_id}_{uuid4().hex[:6]}"
    full = await _run_single(
        scenario_id, full_id, record_fields,
        kb_items_raw=kb_items_raw, prior_cases=prior_cases,
        server_url=server_url, db_path=db_path,
        poll_timeout=poll_timeout, poll_interval=poll_interval,
    )

    # Track relevant vs irrelevant KB IDs
    kb_relevant_ids = []
    kb_irrelevant_ids = []
    for i, item in enumerate(kb_items_raw):
        if i < len(full.get("kb_ids", [])):
            if item.get("relevant", True):
                kb_relevant_ids.append(full["kb_ids"][i])
            else:
                kb_irrelevant_ids.append(full["kb_ids"][i])

    return {
        "scenario_id": scenario_id,
        "doctor_id": full["doctor_id"],
        "record_id": full["record_id"],
        "kb_ids": full.get("kb_ids", []),
        "kb_relevant_ids": kb_relevant_ids,
        "kb_irrelevant_ids": kb_irrelevant_ids,
        "kb_items_meta": kb_items_raw,
        "case_record_ids": full.get("case_record_ids", []),
        "record_fields": record_fields,
        "suggestions": full.get("suggestions", []),
        "baseline_suggestions": baseline_suggestions,
        "error": full.get("error"),
        "diagnosis_time_s": full.get("diagnosis_time_s", 0),
    }
