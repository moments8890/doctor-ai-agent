"""Patient interview API helpers for regression tests.

All endpoints require a patient JWT token (Authorization: Bearer <token>).
The test flow: register patient → get token → use token for interview calls.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import httpx

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


def patient_register(
    server_url: str, doctor_id: str, name: str, gender: str,
    year_of_birth: int, phone: str,
) -> Tuple[int, dict]:
    """POST /api/patient/register. Returns (status_code, body)."""
    payload = {
        "doctor_id": doctor_id,
        "name": name,
        "gender": gender,
        "year_of_birth": year_of_birth,
        "phone": phone,
    }
    resp = httpx.post(f"{server_url}/api/patient/register", json=payload, timeout=_TIMEOUT)
    try:
        body = resp.json()
    except Exception:
        body = {}
    return resp.status_code, body


def patient_login(
    server_url: str, phone: str, year_of_birth: int, doctor_id: Optional[str] = None,
) -> Tuple[int, dict]:
    """POST /api/patient/login. Returns (status_code, body)."""
    payload = {"phone": phone, "year_of_birth": year_of_birth}
    if doctor_id:
        payload["doctor_id"] = doctor_id
    resp = httpx.post(f"{server_url}/api/patient/login", json=payload, timeout=_TIMEOUT)
    try:
        body = resp.json()
    except Exception:
        body = {}
    return resp.status_code, body


def _auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def patient_interview_start(server_url: str, token: str) -> dict:
    """POST /api/patient/interview/start. Returns session info."""
    resp = httpx.post(
        f"{server_url}/api/patient/interview/start",
        headers=_auth_header(token), timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def patient_interview_turn(server_url: str, token: str, session_id: str, text: str) -> dict:
    """POST /api/patient/interview/turn. Returns interview response."""
    resp = httpx.post(
        f"{server_url}/api/patient/interview/turn",
        json={"session_id": session_id, "text": text},
        headers=_auth_header(token), timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def patient_interview_confirm(server_url: str, token: str, session_id: str) -> Tuple[int, dict]:
    """POST /api/patient/interview/confirm. Returns (status_code, body)."""
    resp = httpx.post(
        f"{server_url}/api/patient/interview/confirm",
        json={"session_id": session_id},
        headers=_auth_header(token), timeout=_TIMEOUT,
    )
    try:
        body = resp.json()
    except Exception:
        body = {}
    return resp.status_code, body


def patient_interview_cancel(server_url: str, token: str, session_id: str) -> Tuple[int, dict]:
    """POST /api/patient/interview/cancel. Returns (status_code, body)."""
    resp = httpx.post(
        f"{server_url}/api/patient/interview/cancel",
        json={"session_id": session_id},
        headers=_auth_header(token), timeout=_TIMEOUT,
    )
    try:
        body = resp.json()
    except Exception:
        body = {}
    return resp.status_code, body


def patient_interview_current(server_url: str, token: str) -> Optional[dict]:
    """GET /api/patient/interview/current. Returns session or None."""
    resp = httpx.get(
        f"{server_url}/api/patient/interview/current",
        headers=_auth_header(token), timeout=_TIMEOUT,
    )
    if resp.status_code == 200:
        return resp.json()
    return None
