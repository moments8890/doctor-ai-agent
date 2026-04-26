"""Unified authentication for doctors and patients.

Single JWT system with role-based access. Both roles log in with a nickname
and a numeric passcode. The passcode is PBKDF2-SHA256 hashed at rest.
Doctors require an invitation code at sign-up (one-time).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import Header, HTTPException

from infra.auth import UserRole
from utils.hashing import hash_passcode, verify_passcode
from utils.log import log

_TOKEN_TTL = int(os.environ.get("UNIFIED_TOKEN_TTL", "604800"))  # 7 days default
_AUDIENCE = "doctor-ai-agent"

# Brute-force defense: lock the account after N consecutive failures.
# Defaults: 5 attempts → 7-day lock. Tunable via env so a stuck user can be
# given relief without redeploy.
_LOGIN_FAIL_THRESHOLD = int(os.environ.get("LOGIN_FAIL_THRESHOLD", "5"))
_LOGIN_LOCK_SECONDS = int(os.environ.get("LOGIN_LOCK_SECONDS", str(7 * 86400)))


def _dummy_hash() -> str:
    """A real PBKDF2 hash of a dummy passcode, used to equalize timing on
    the not-found path so an attacker can't enumerate valid nicknames by
    measuring response latency. Computed once and cached in module state.
    """
    if not hasattr(_dummy_hash, "_cached"):
        _dummy_hash._cached = hash_passcode("dummy-passcode-for-timing-parity-only")  # type: ignore[attr-defined]
    return _dummy_hash._cached  # type: ignore[attr-defined]


def _secret() -> str:
    secret = os.environ.get("UNIFIED_AUTH_SECRET", "")
    if not secret:
        env = os.environ.get("ENVIRONMENT", "").strip().lower()
        if env not in ("development", "dev", "test"):
            raise RuntimeError("UNIFIED_AUTH_SECRET must be set in production.")
        secret = "dev-unified-secret-change-me"
    return secret


def issue_token(
    role: str,
    doctor_id: Optional[str] = None,
    patient_id: Optional[int] = None,
    name: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    passcode_version: int = 1,
) -> str:
    """Issue a unified JWT token.

    The ``pcv`` claim is the user's current ``passcode_version``; bumping the
    column on the user row invalidates every token previously issued with the
    old number (logout, passcode change, "log out everywhere" all bump it).
    """
    now = int(time.time())
    payload = {
        "role": role,  # "doctor" or "patient"
        "doctor_id": doctor_id,
        "patient_id": patient_id,
        "name": name,
        "pcv": passcode_version,
        "aud": _AUDIENCE,
        "iat": now,
        "exp": now + (ttl_seconds if ttl_seconds is not None else _TOKEN_TTL),
    }
    # Set sub based on role
    if role == UserRole.doctor:
        payload["sub"] = doctor_id
    else:
        payload["sub"] = str(patient_id)
    return jwt.encode(payload, _secret(), algorithm="HS256")


def verify_token(token: str) -> dict:
    """Verify JWT and return payload. Raises HTTPException on failure."""
    if not token:
        raise HTTPException(401, "Missing token")
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"], audience=_AUDIENCE)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    return payload


def extract_token(authorization: Optional[str] = None) -> str:
    """Extract Bearer token from Authorization header."""
    if not authorization:
        raise HTTPException(401, "Authorization header required")
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return authorization


async def authenticate(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Authenticate from Authorization header. Returns JWT payload.

    Also verifies the token's ``pcv`` claim against the user's current
    ``passcode_version`` in the DB; mismatch means the user has logged out
    everywhere or rotated their passcode, so the token is rejected.
    """
    token = extract_token(authorization)
    payload = verify_token(token)
    await _enforce_passcode_version(payload)
    return payload


async def _enforce_passcode_version(payload: dict) -> None:
    """Reject tokens whose pcv doesn't match the user's current passcode_version."""
    token_pcv = payload.get("pcv")
    # Tokens issued before this feature shipped don't carry pcv; treat as 1
    # (the default) for grandfather compatibility. Bumping pcv to 2+ on the
    # user row will then invalidate them.
    if token_pcv is None:
        token_pcv = 1

    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select

    role = payload.get("role")
    async with AsyncSessionLocal() as db:
        if role == UserRole.doctor:
            row = (await db.execute(
                select(Doctor).where(Doctor.doctor_id == payload.get("doctor_id"))
            )).scalar_one_or_none()
        elif role == UserRole.patient:
            row = (await db.execute(
                select(Patient).where(Patient.id == payload.get("patient_id"))
            )).scalar_one_or_none()
        else:
            return  # unknown role — let downstream role guards reject

    # Missing user row = the principal no longer exists (e.g., forget_me
    # deleted them). The token must NOT be honored as if pcv=1 still
    # matched. Reject with the same shape as a revoked token.
    if row is None:
        raise HTTPException(401, "Token revoked")

    current_pcv = row.passcode_version or 1
    if int(token_pcv) != int(current_pcv):
        raise HTTPException(401, "Token revoked")


async def forget_me(role: str, doctor_id: Optional[str] = None, patient_id: Optional[int] = None, passcode: str = "") -> dict:
    """Right-to-be-forgotten: hard-delete the calling user's row.

    Requires the caller's current passcode as a re-confirmation gate, so an
    XSS or stolen-token attack can't silently destroy an account. The MySQL
    FK CASCADE rules clean up dependent rows (records, messages, suggestions,
    drafts, etc.) — see migration ``a4b5c6d7e8f9``.

    The audit_log row uses ``ondelete="SET NULL"`` on doctor_id, so the
    history of actions stays intact for compliance, just unattributed.
    """
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select, delete

    async with AsyncSessionLocal() as db:
        if role == UserRole.doctor:
            row = (await db.execute(
                select(Doctor).where(Doctor.doctor_id == doctor_id)
            )).scalar_one_or_none()
        elif role == UserRole.patient:
            row = (await db.execute(
                select(Patient).where(Patient.id == patient_id)
            )).scalar_one_or_none()
        else:
            raise HTTPException(400, "Invalid role")
        if row is None:
            raise HTTPException(404, "User not found")

        # Re-verify passcode. Failed attempt counter is irrelevant here —
        # we don't want a destructive action to also lock you out.
        if not row.passcode_hash or not verify_passcode(passcode, row.passcode_hash):
            raise HTTPException(401, "口令错误，操作已取消")

        if role == UserRole.doctor:
            log(f"[auth] doctor forget-me id={doctor_id}")
            await db.execute(delete(Doctor).where(Doctor.doctor_id == doctor_id))
        else:
            log(f"[auth] patient forget-me id={patient_id}")
            await db.execute(delete(Patient).where(Patient.id == patient_id))
        await db.commit()

    return {"ok": True, "deleted_role": role}


async def revoke_user_tokens(role: str, doctor_id: Optional[str] = None, patient_id: Optional[int] = None) -> None:
    """Bump the user's passcode_version, killing all previously issued tokens."""
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        if role == UserRole.doctor:
            row = (await db.execute(
                select(Doctor).where(Doctor.doctor_id == doctor_id)
            )).scalar_one_or_none()
        elif role == UserRole.patient:
            row = (await db.execute(
                select(Patient).where(Patient.id == patient_id)
            )).scalar_one_or_none()
        else:
            raise HTTPException(400, "Invalid role")
        if row is None:
            raise HTTPException(404, "User not found")
        row.passcode_version = (row.passcode_version or 1) + 1
        await db.commit()


async def require_doctor(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Authenticate and require doctor role."""
    payload = await authenticate(authorization)
    if payload.get("role") != UserRole.doctor:
        raise HTTPException(403, "Doctor access required")
    return payload


async def require_patient(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Authenticate and require patient role."""
    payload = await authenticate(authorization)
    if payload.get("role") != UserRole.patient:
        raise HTTPException(403, "Patient access required")
    return payload


def _is_locked(record) -> bool:
    locked_until = getattr(record, "passcode_locked_until", None)
    if locked_until is None:
        return False
    return locked_until > datetime.now(timezone.utc).replace(tzinfo=None)


async def _atomic_record_login_failure(db, model, pk_col, pk_value) -> None:
    """Atomically increment failure counter and set lock when threshold trips.

    Single SQL UPDATE so two parallel bad guesses can't both read counter=N,
    write N+1, and effectively skip an increment. The lock_until column is
    set via CASE so the threshold check happens server-side.
    """
    from datetime import timedelta
    from sqlalchemy import case, update
    lock_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=_LOGIN_LOCK_SECONDS)
    new_attempts = model.passcode_failed_attempts + 1
    await db.execute(
        update(model)
        .where(pk_col == pk_value)
        .values(
            passcode_failed_attempts=new_attempts,
            passcode_locked_until=case(
                (new_attempts >= _LOGIN_FAIL_THRESHOLD, lock_at),
                else_=model.passcode_locked_until,
            ),
        )
    )


async def _atomic_record_login_success(db, model, pk_col, pk_value) -> None:
    """Atomically clear failure counter + lock on a successful login."""
    from sqlalchemy import update
    await db.execute(
        update(model)
        .where(pk_col == pk_value)
        .values(passcode_failed_attempts=0, passcode_locked_until=None)
    )


async def login(nickname: str, passcode: str, role: Optional[str] = None) -> dict:
    """Login with nickname + passcode. Optional `role` constrains the search.

    Doctor and patient accounts are independent — the same nickname can exist
    in both roles. The login UI declares which role the user is signing in as
    via the active tab; we honor that here so doctors don't see a redundant
    role picker just because a patient happens to share their nickname.

    The passcode is verified against the PBKDF2-SHA256 hash stored in
    ``passcode_hash``; the legacy ``phone`` / ``year_of_birth`` columns are
    no longer consulted.

    Returns:
        - Single match: {token, role, doctor_id, patient_id, name}
        - Multiple matches (role unset): {needs_role_selection: True, roles: [...]}
        - No match: raises 401
    """
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select

    if role is not None and role not in (UserRole.doctor, UserRole.patient):
        raise HTTPException(400, "role must be 'doctor' or 'patient'")

    results = []
    # Track which row to penalize on failure. We only mutate counters when
    # the (nickname, role) tuple narrows to ONE row — otherwise an attacker
    # could lock out unrelated accounts that happen to share a nickname.
    sole_doctor = None
    sole_patient = None
    matched_passcode = False  # True iff at least one passcode_hash verified

    async with AsyncSessionLocal() as db:
        if role in (None, UserRole.doctor):
            doctors = (await db.execute(
                select(Doctor).where(Doctor.nickname == nickname)
            )).scalars().all()
            if len(doctors) == 1:
                sole_doctor = doctors[0]
            for d in doctors:
                if _is_locked(d):
                    continue
                if d.passcode_hash and verify_passcode(passcode, d.passcode_hash):
                    matched_passcode = True
                    await _atomic_record_login_success(db, Doctor, Doctor.doctor_id, d.doctor_id)
                    results.append({
                        "role": UserRole.doctor,
                        "doctor_id": d.doctor_id,
                        "patient_id": None,
                        "name": d.name or d.doctor_id,
                        "passcode_version": d.passcode_version or 1,
                    })

        if role in (None, UserRole.patient):
            patients = (await db.execute(
                select(Patient).where(Patient.nickname == nickname)
            )).scalars().all()
            if len(patients) == 1:
                sole_patient = patients[0]
            for p in patients:
                if _is_locked(p):
                    continue
                if p.passcode_hash and verify_passcode(passcode, p.passcode_hash):
                    matched_passcode = True
                    await _atomic_record_login_success(db, Patient, Patient.id, p.id)
                    results.append({
                        "role": UserRole.patient,
                        "doctor_id": p.doctor_id,
                        "patient_id": p.id,
                        "name": p.name,
                        "passcode_version": p.passcode_version or 1,
                    })

        # Failure path. Counter mutation rules — DOS prevention:
        #   - Only mutate the counter when (nickname, role) narrows to ONE
        #     row within that role (sole_doctor / sole_patient).
        #   - When BOTH a sole_doctor AND a sole_patient exist (the same
        #     nickname coexists across roles), mutating EITHER would let an
        #     attacker who knows the nickname is shared lock out both
        #     accounts in one campaign. Skip both — the user can retry with
        #     an explicit role to penalize the right one.
        #   - When a sole candidate exists but is locked, run a dummy hash
        #     verify so an attacker can't distinguish "active" from "locked"
        #     via response latency.
        if not matched_passcode:
            cross_role_ambiguous = (sole_doctor is not None and sole_patient is not None)

            if cross_role_ambiguous:
                # Same nickname in both roles, no role hint — refuse to
                # penalize either account.
                verify_passcode(passcode, _dummy_hash())
            elif sole_doctor is not None:
                if _is_locked(sole_doctor):
                    verify_passcode(passcode, _dummy_hash())  # timing parity
                else:
                    await _atomic_record_login_failure(db, Doctor, Doctor.doctor_id, sole_doctor.doctor_id)
            elif sole_patient is not None:
                if _is_locked(sole_patient):
                    verify_passcode(passcode, _dummy_hash())  # timing parity
                else:
                    await _atomic_record_login_failure(db, Patient, Patient.id, sole_patient.id)
            else:
                # No candidate at all — dummy verify keeps timing comparable.
                verify_passcode(passcode, _dummy_hash())

        await db.commit()

    if not results:
        # Uniform 401 for all failure modes (locked / wrong passcode / no
        # such nickname). Distinct status codes leak account state.
        raise HTTPException(401, "昵称或口令不正确")

    if len(results) == 1:
        r = results[0]
        pcv = r.pop("passcode_version")
        token = issue_token(r["role"], r["doctor_id"], r["patient_id"], r["name"], passcode_version=pcv)
        return {"token": token, **r}

    # Multiple matches: don't leak passcode_version to caller — it's only
    # needed at the next login-with-role hop, which re-derives it from DB.
    for r in results:
        r.pop("passcode_version", None)
    return {
        "needs_role_selection": True,
        "roles": results,
    }


async def login_with_role(nickname: str, passcode: str, role: str, doctor_id: Optional[str] = None, patient_id: Optional[int] = None) -> dict:
    """Login with explicit role selection (after role picker)."""
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        if role == UserRole.doctor:
            doctor = (await db.execute(
                select(Doctor).where(Doctor.nickname == nickname)
            )).scalar_one_or_none()
            # Order matters: don't run verify_passcode on a locked account
            # (it would skip the timing-parity dummy below, and we don't
            # want the lock to be observable via latency).
            if doctor is None:
                verify_passcode(passcode, _dummy_hash())
                raise HTTPException(401, "登录失败")
            if _is_locked(doctor):
                verify_passcode(passcode, _dummy_hash())
                raise HTTPException(401, "登录失败")
            if not doctor.passcode_hash or not verify_passcode(passcode, doctor.passcode_hash):
                await _atomic_record_login_failure(db, Doctor, Doctor.doctor_id, doctor.doctor_id)
                await db.commit()
                raise HTTPException(401, "登录失败")
            await _atomic_record_login_success(db, Doctor, Doctor.doctor_id, doctor.doctor_id)
            await db.commit()
            token = issue_token(
                UserRole.doctor, doctor.doctor_id, None, doctor.name,
                passcode_version=doctor.passcode_version or 1,
            )
            return {"token": token, "role": UserRole.doctor, "doctor_id": doctor.doctor_id, "name": doctor.name}

        elif role == UserRole.patient:
            # DOS prevention: a patient login MUST narrow to one row before
            # we mutate any failure counter. Without doctor_id or patient_id,
            # an attacker hammering "alice" would lock out every patient
            # with that nickname across all doctors.
            if not patient_id and not doctor_id:
                raise HTTPException(400, "patient login requires doctor_id or patient_id")
            stmt = select(Patient).where(Patient.nickname == nickname)
            if patient_id:
                stmt = stmt.where(Patient.id == patient_id)
            elif doctor_id:
                stmt = stmt.where(Patient.doctor_id == doctor_id)
            candidates = (await db.execute(stmt)).scalars().all()
            # Find the unique unlocked candidate that matches the passcode.
            patient = None
            for p in candidates:
                if _is_locked(p):
                    continue
                if p.passcode_hash and verify_passcode(passcode, p.passcode_hash):
                    patient = p
                    break
            if patient is None:
                # Only mutate the counter when the selector narrows to ONE
                # row; multi-candidate misses fail fast without touching
                # any account. Locked-but-unique candidate gets a timing-
                # parity dummy verify, no counter movement.
                if len(candidates) == 1 and not _is_locked(candidates[0]):
                    await _atomic_record_login_failure(db, Patient, Patient.id, candidates[0].id)
                    await db.commit()
                else:
                    verify_passcode(passcode, _dummy_hash())
                raise HTTPException(401, "登录失败")
            await _atomic_record_login_success(db, Patient, Patient.id, patient.id)
            await db.commit()
            token = issue_token(
                UserRole.patient, patient.doctor_id, patient.id, patient.name,
                passcode_version=patient.passcode_version or 1,
            )
            return {"token": token, "role": UserRole.patient, "doctor_id": patient.doctor_id, "patient_id": patient.id, "name": patient.name}

    raise HTTPException(400, "Invalid role")


async def register_doctor(nickname: str, passcode: str, invite_code: str, specialty: Optional[str] = None) -> dict:
    """Register a new doctor with invitation code.

    Stores ``nickname`` and ``passcode_hash`` (PBKDF2-SHA256). The display
    ``name`` defaults to the nickname; profile editing can change it later.
    """
    from db.engine import AsyncSessionLocal
    from db.models import Doctor
    from db.models.doctor import InviteCode
    from sqlalchemy import select
    import secrets

    async with AsyncSessionLocal() as db:
        code_row = (await db.execute(
            select(InviteCode).where(InviteCode.code == invite_code)
        )).scalar_one_or_none()

        if code_row is None or not code_row.active:
            raise HTTPException(400, "邀请码无效")
        if code_row.expires_at and code_row.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(400, "邀请码已过期")
        if code_row.max_uses > 0 and code_row.used_count >= code_row.max_uses:
            raise HTTPException(400, "邀请码已被使用")

        existing = (await db.execute(
            select(Doctor).where(Doctor.nickname == nickname)
            .where(~Doctor.doctor_id.like("inttest_%"))
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(400, "该昵称已被注册，请换一个或直接登录")

        doctor_id = f"inv_{secrets.token_urlsafe(9)}"
        doctor = Doctor(
            doctor_id=doctor_id,
            name=nickname,
            nickname=nickname,
            passcode_hash=hash_passcode(passcode),
            specialty=specialty,
        )
        db.add(doctor)

        code_row.used_count += 1
        if not code_row.doctor_id:
            code_row.doctor_id = doctor_id

        await db.commit()

    # Don't log nickname — that's a user-typed credential identifier.
    # doctor_id is a synthetic random ID, safe to log for correlation.
    log(f"[auth] doctor registered id={doctor_id}")
    token = issue_token(UserRole.doctor, doctor_id, None, nickname, passcode_version=1)
    return {"token": token, "role": UserRole.doctor, "doctor_id": doctor_id, "name": nickname}


async def register_patient(nickname: str, passcode: str, doctor_id: str, gender: Optional[str] = None) -> dict:
    """Register a new patient under a doctor.

    Uniqueness is scoped per doctor: (doctor_id, nickname). The display
    ``name`` defaults to the nickname.
    """
    from db.engine import AsyncSessionLocal
    from db.models import Doctor, Patient
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        doctor = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == doctor_id)
        )).scalar_one_or_none()
        if doctor is None:
            raise HTTPException(404, "未找到该医生")

        existing = (await db.execute(
            select(Patient).where(
                Patient.doctor_id == doctor_id,
                Patient.nickname == nickname,
            )
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(400, "该昵称已被注册，请换一个或直接登录")

        patient = Patient(
            doctor_id=doctor_id,
            name=nickname,
            nickname=nickname,
            passcode_hash=hash_passcode(passcode),
            gender=gender,
        )
        db.add(patient)
        await db.commit()
        await db.refresh(patient)

    # patient.id + doctor_id are synthetic, nickname is user-typed.
    log(f"[auth] patient registered id={patient.id} doctor={doctor_id}")
    token = issue_token(UserRole.patient, doctor_id, patient.id, nickname, passcode_version=1)
    return {"token": token, "role": UserRole.patient, "doctor_id": doctor_id, "patient_id": patient.id, "name": nickname}


async def register_patient_by_attach_code(
    nickname: str,
    passcode: str,
    attach_code: str,
    gender: Optional[str] = None,
) -> Optional[dict]:
    """Register a patient under the doctor identified by ``attach_code``.

    Returns the same dict shape as :func:`register_patient` on success, or
    ``None`` on ANY failure (invalid code, doctor not found, duplicate
    nickname, missing field, etc.). The route handler is responsible for
    converting None into a generic oracle-safe error response — this helper
    must never raise an HTTPException with a detail string that reveals
    which failure mode fired.
    """
    from db.engine import AsyncSessionLocal
    from db.models import Doctor
    from sqlalchemy import select

    if not attach_code or len(attach_code) < 4:
        return None
    async with AsyncSessionLocal() as db:
        doctor = (await db.execute(
            select(Doctor).where(Doctor.patient_attach_code == attach_code)
        )).scalar_one_or_none()
        if doctor is None:
            log(f"[auth] patient register: invalid attach_code prefix={attach_code[:2]}**")
            return None
    # Hand off to the standard registration path. We swallow the HTTPException
    # variants (duplicate nickname etc.) and convert them into None so the
    # caller can return the generic oracle-safe envelope.
    try:
        return await register_patient(nickname, passcode, doctor.doctor_id, gender)
    except HTTPException as exc:
        log(f"[auth] patient register: failure code_prefix={attach_code[:2]}** status={exc.status_code}")
        return None
    except Exception as exc:
        log(f"[auth] patient register: unexpected exception {type(exc).__name__}: {exc}")
        return None
