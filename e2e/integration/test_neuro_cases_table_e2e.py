"""神经病例持久化端到端覆盖测试（medical_records, record_type='neuro_case'）。

E2E coverage for neuro case persistence.

Starts from doctor natural language input to `/api/neuro/from-text`,
then verifies row persistence in `medical_records` (record_type='neuro_case')
and API visibility.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid

import httpx
import pytest

from e2e.integration.conftest import DB_PATH, SERVER


def _neuro_row(case_id: int, doctor_id: str) -> dict | None:
    """Load a neuro_case row from medical_records by id + doctor_id."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT id, doctor_id, neuro_patient_name, neuro_raw_json, record_type, nihss
            FROM medical_records
            WHERE id=? AND doctor_id=? AND record_type='neuro_case'
            """,
            (case_id, doctor_id),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "doctor_id": row[1],
            "neuro_patient_name": row[2],
            "neuro_raw_json": row[3],
            "record_type": row[4],
            "nihss": row[5],
        }
    finally:
        conn.close()


def _post_neuro_from_text(text: str, doctor_id: str) -> dict:
    read_timeout = float(os.environ.get("CHAT_TIMEOUT", "300"))
    retries = int(os.environ.get("CHAT_RETRIES", "1"))
    timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=10.0)
    payload = {"doctor_id": doctor_id, "text": text}

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                f"{SERVER}/api/neuro/from-text",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(2)
                continue
            break
    raise RuntimeError(
        f"neuro from-text request failed after {retries + 1} attempt(s); "
        f"read_timeout={read_timeout}s; doctor_id={doctor_id}"
    ) from last_exc


@pytest.mark.integration
def test_neuro_table_insert_from_human_language_e2e():
    doctor_id = f"inttest_neuro_table_{uuid.uuid4().hex[:8]}"
    patient_name = "神经专科患者甲"

    payload = _post_neuro_from_text(
        text=f"{patient_name}，男，68岁，突发言语含糊3小时，右上肢乏力，拟卒中流程评估。",
        doctor_id=doctor_id,
    )
    case_id = int(payload["db_id"])

    row = _neuro_row(case_id, doctor_id)
    assert row is not None, "medical_records neuro_case row should be inserted"
    assert row["doctor_id"] == doctor_id
    assert row["record_type"] == "neuro_case"
    if row["neuro_patient_name"] is not None:
        assert patient_name in row["neuro_patient_name"]

    # Clinical content should appear in the serialised neuro_raw_json
    neuro_blob = row["neuro_raw_json"] or ""
    assert ("言语" in neuro_blob) or ("乏力" in neuro_blob) or ("卒中" in neuro_blob), (
        f"Expected clinical tokens not found in neuro_raw_json"
    )

    listed = httpx.get(
        f"{SERVER}/api/neuro/cases",
        params={"doctor_id": doctor_id, "limit": 20},
        timeout=30,
    )
    listed.raise_for_status()
    items = listed.json()
    assert any(int(item["id"]) == case_id for item in items)
