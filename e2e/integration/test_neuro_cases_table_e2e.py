"""E2E coverage for neuro_cases table persistence.

Starts from doctor natural language input to `/api/neuro/from-text`,
then verifies row persistence in `neuro_cases` and API visibility.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid

import httpx
import pytest

from e2e.integration.conftest import DB_PATH, SERVER


def _neuro_row(case_id: int, doctor_id: str) -> tuple | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(
            """
            SELECT id, doctor_id, patient_name, chief_complaint, primary_diagnosis, nihss
            FROM neuro_cases
            WHERE id=? AND doctor_id=?
            """,
            (case_id, doctor_id),
        ).fetchone()
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
    assert row is not None, "neuro_cases row should be inserted"
    assert row[1] == doctor_id
    if row[2] is not None:
        assert patient_name in row[2]
    assert (row[3] or "").strip() != ""
    neuro_blob = "{0}\n{1}".format(row[3] or "", row[4] or "")
    assert ("言语" in neuro_blob) or ("乏力" in neuro_blob) or ("卒中" in neuro_blob)

    listed = httpx.get(
        f"{SERVER}/api/neuro/cases",
        params={"doctor_id": doctor_id, "limit": 20},
        timeout=30,
    )
    listed.raise_for_status()
    items = listed.json()
    assert any(int(item["id"]) == case_id for item in items)
