"""
Patient portal authentication helpers: token creation, verification, and
patient authentication middleware.

Shared by both the main patient portal routes and the registration routes.
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any, Optional

import jwt
from fastapi import HTTPException
from sqlalchemy import select

from db.engine import AsyncSessionLocal
from db.models import Patient
from infra.auth.access_code_hash import hash_access_code, verify_access_code

logger = logging.getLogger(__name__)

# Pre-computed PBKDF2 hash of "000000" used as a timing-equaliser when
# the patient lookup misses.  Generated once at import time.
_DUMMY_HASH: str = hash_access_code("000000")

_AUTH_FAIL = "\u59d3\u540d\u3001\u533b\u751f\u7f16\u53f7\u6216\u8bbf\u95ee\u7801\u4e0d\u6b63\u786e\uff0c\u8bf7\u91cd\u65b0\u786e\u8ba4\u3002"

# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

_TOKEN_TTL = 86400  # 24 hours

_PATIENT_TOKEN_AUD = "patient_portal"


def _portal_secret() -> str:
    secret = os.environ.get("PATIENT_PORTAL_SECRET", "").strip()
    if not secret:
        from infra.auth import is_production
        if is_production():
            raise RuntimeError(
                "PATIENT_PORTAL_SECRET must be set in production."
            )
        secret = "dev-patient-secret"
    return secret


def _issue_patient_token(
    patient_id: int, doctor_id: str, access_code_version: int = 0,
) -> str:
    now = int(time.time())
    payload = {
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "acv": access_code_version,
        "aud": _PATIENT_TOKEN_AUD,
        "iat": now,
        "exp": now + _TOKEN_TTL,
    }
    return jwt.encode(payload, _portal_secret(), algorithm="HS256")


def _verify_patient_token(token: str) -> dict:
    """Verify JWT and return decoded payload dict, or raise HTTPException.

    The caller must check ``acv`` against the patient's current
    ``access_code_version`` to ensure the token hasn't been revoked by
    an access-code rotation.
    """
    token = (token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing patient token")
    try:
        payload = jwt.decode(
            token, _portal_secret(), algorithms=["HS256"],
            audience=_PATIENT_TOKEN_AUD,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Patient token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid patient token")

    patient_id = payload.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=401, detail="Token missing patient_id")
    return {
        "patient_id": int(patient_id),
        "doctor_id": payload.get("doctor_id"),
        "acv": payload.get("acv", 0),
    }


async def _authenticate_patient(
    x_patient_token: Optional[str] = None,
    authorization: Optional[str] = None,
) -> Patient:
    """Validate patient via X-Patient-Token or Authorization: Bearer token (unified auth).

    Tries X-Patient-Token first, falls back to Authorization header.
    Returns the Patient ORM instance on success; raises HTTPException otherwise.
    """
    bearer = x_patient_token or authorization
    if bearer and bearer.startswith("Bearer "):
        bearer = bearer[7:]
    if not bearer:
        raise HTTPException(status_code=401, detail="Authentication required")

    from infra.auth.unified import verify_token
    from infra.auth import UserRole

    try:
        payload = verify_token(bearer)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("role") != UserRole.patient:
        raise HTTPException(403, "Patient access required")

    patient_id = payload.get("patient_id")
    token_doctor_id = payload.get("doctor_id")

    async with AsyncSessionLocal() as db:
        stmt = select(Patient).where(Patient.id == patient_id)
        if token_doctor_id:
            stmt = stmt.where(Patient.doctor_id == token_doctor_id)
        patient = (await db.execute(stmt.limit(1))).scalar_one_or_none()

    if patient is None:
        raise HTTPException(404, "Patient not found")
    return patient


async def _lookup_patient_by_name(doctor_id: str, patient_name: str) -> "Patient | None":
    """Exact-name lookup of a patient within a doctor's namespace."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Patient)
            .where(Patient.doctor_id == doctor_id, Patient.name == patient_name)
            .limit(1)
        )
        return result.scalar_one_or_none()


def _verify_patient_access_code(auth_row: "Optional[Any]", supplied_code: str) -> None:
    """Validate the access code against the PatientAuth row.

    - PatientAuth row **exists** with an access_code hash -> supplied code must match.
    - No PatientAuth row (legacy patient, no access code) -> reject with 403.
    """
    if auth_row is None or not getattr(auth_row, "access_code", None):
        # Legacy patient -- no access code configured yet.
        # Reject login: name-only auth is too weak for medical data.
        logger.warning(
            "[PatientPortal] BLOCKED: name-only login "
            "(no access_code set). Migrate this patient via POST /api/patient/access-code.",
        )
        raise HTTPException(
            status_code=403,
            detail="\u8be5\u60a3\u8005\u5c1a\u672a\u8bbe\u7f6e\u8bbf\u95ee\u7801\uff0c\u8bf7\u8054\u7cfb\u60a8\u7684\u533b\u751f\u83b7\u53d6\u8bbf\u95ee\u7801\u3002",
        )
    if not supplied_code or not verify_access_code(supplied_code, auth_row.access_code):
        raise HTTPException(status_code=401, detail=_AUTH_FAIL)
