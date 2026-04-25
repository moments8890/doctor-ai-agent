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

_TOKEN_TTL = int(os.environ.get("UNIFIED_TOKEN_TTL", "31536000"))  # 1 year default
_AUDIENCE = "doctor-ai-agent"

# Brute-force defense: lock the account after N consecutive failures.
# Defaults: 5 attempts → 7-day lock. Tunable via env so a stuck user can be
# given relief without redeploy.
_LOGIN_FAIL_THRESHOLD = int(os.environ.get("LOGIN_FAIL_THRESHOLD", "5"))
_LOGIN_LOCK_SECONDS = int(os.environ.get("LOGIN_LOCK_SECONDS", str(7 * 86400)))


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
            doctor = (await db.execute(
                select(Doctor).where(Doctor.doctor_id == payload.get("doctor_id"))
            )).scalar_one_or_none()
            current_pcv = (doctor.passcode_version if doctor else None) or 1
        elif role == UserRole.patient:
            patient = (await db.execute(
                select(Patient).where(Patient.id == payload.get("patient_id"))
            )).scalar_one_or_none()
            current_pcv = (patient.passcode_version if patient else None) or 1
        else:
            return  # unknown role — let downstream role guards reject

    if int(token_pcv) != int(current_pcv):
        raise HTTPException(401, "Token revoked")


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


def _record_login_failure(record) -> bool:
    """Increment the failure counter on a record; lock when threshold hit.

    Caller must commit. Returns True if this attempt tripped a fresh lock.
    """
    record.passcode_failed_attempts = (record.passcode_failed_attempts or 0) + 1
    if record.passcode_failed_attempts >= _LOGIN_FAIL_THRESHOLD:
        from datetime import timedelta
        record.passcode_locked_until = (
            datetime.now(timezone.utc).replace(tzinfo=None)
            + timedelta(seconds=_LOGIN_LOCK_SECONDS)
        )
        return True
    return False


def _record_login_success(record) -> None:
    record.passcode_failed_attempts = 0
    record.passcode_locked_until = None


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
    locked_any = False

    async with AsyncSessionLocal() as db:
        if role in (None, UserRole.doctor):
            doctors = (await db.execute(
                select(Doctor).where(Doctor.nickname == nickname)
            )).scalars().all()
            for d in doctors:
                if _is_locked(d):
                    locked_any = True
                    continue
                if d.passcode_hash and verify_passcode(passcode, d.passcode_hash):
                    _record_login_success(d)
                    results.append({
                        "role": UserRole.doctor,
                        "doctor_id": d.doctor_id,
                        "patient_id": None,
                        "name": d.name or d.doctor_id,
                        "passcode_version": d.passcode_version or 1,
                    })
                else:
                    _record_login_failure(d)

        if role in (None, UserRole.patient):
            patients = (await db.execute(
                select(Patient).where(Patient.nickname == nickname)
            )).scalars().all()
            for p in patients:
                if _is_locked(p):
                    locked_any = True
                    continue
                if p.passcode_hash and verify_passcode(passcode, p.passcode_hash):
                    _record_login_success(p)
                    results.append({
                        "role": UserRole.patient,
                        "doctor_id": p.doctor_id,
                        "patient_id": p.id,
                        "name": p.name,
                        "passcode_version": p.passcode_version or 1,
                    })
                else:
                    _record_login_failure(p)

        await db.commit()  # persist failure counter / lock / reset

    if not results:
        if locked_any:
            raise HTTPException(
                423,
                f"账号已锁定（{_LOGIN_LOCK_SECONDS // 86400} 天后自动解锁），请稍后再试或联系管理员",
            )
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
            if doctor and _is_locked(doctor):
                raise HTTPException(423, "账号已锁定，请稍后再试或联系管理员")
            if not doctor or not doctor.passcode_hash or not verify_passcode(passcode, doctor.passcode_hash):
                if doctor:
                    _record_login_failure(doctor)
                    await db.commit()
                raise HTTPException(401, "登录失败")
            _record_login_success(doctor)
            await db.commit()
            token = issue_token(
                UserRole.doctor, doctor.doctor_id, None, doctor.name,
                passcode_version=doctor.passcode_version or 1,
            )
            return {"token": token, "role": UserRole.doctor, "doctor_id": doctor.doctor_id, "name": doctor.name}

        elif role == UserRole.patient:
            stmt = select(Patient).where(Patient.nickname == nickname)
            if patient_id:
                stmt = stmt.where(Patient.id == patient_id)
            elif doctor_id:
                stmt = stmt.where(Patient.doctor_id == doctor_id)
            candidates = (await db.execute(stmt)).scalars().all()
            unlocked = [p for p in candidates if not _is_locked(p)]
            if candidates and not unlocked:
                raise HTTPException(423, "账号已锁定，请稍后再试或联系管理员")
            patient = next(
                (p for p in unlocked if p.passcode_hash and verify_passcode(passcode, p.passcode_hash)),
                None,
            )
            if not patient:
                for p in unlocked:
                    _record_login_failure(p)
                await db.commit()
                raise HTTPException(401, "登录失败")
            _record_login_success(patient)
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

    log(f"[auth] doctor registered id={doctor_id} nickname={nickname}")
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

    log(f"[auth] patient registered id={patient.id} nickname={nickname} doctor={doctor_id}")
    token = issue_token(UserRole.patient, doctor_id, patient.id, nickname, passcode_version=1)
    return {"token": token, "role": UserRole.patient, "doctor_id": doctor_id, "patient_id": patient.id, "name": nickname}
