# Patient Attach Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.
>
> **Project rules in force:** never push, work on main branch (no feature branches), commit per task only when the task instructions say to commit, e2e on :8001 only.

**Goal:** Replace the public-doctor-id patient registration flow with a per-doctor permanent 4-char attach code. Doctors share via QR (deep-link) or verbal code; patients enter the code to bind. Drop the public doctor enumeration endpoint. Implement oracle-safe registration to prevent code enumeration via response-shape leaks.

**Architecture:** New `patient_attach_code` column on `doctors` (VARCHAR(8) for future headroom; v0 generates 4 chars from a 32-char alphabet). Backfill at deploy time so every existing doctor has a code on first login post-deploy. New doctor-side endpoint `GET /api/manage/patient-attach-code` returns the code + a deep-link QR URL. Patient registration endpoint switches from `doctor_id` to `attach_code`, normalizes to uppercase, and uses oracle-safe error responses (identical shape, deterministic minimum timing) to defeat enumeration. Rate-limit per IP. Drop `GET /api/auth/unified/doctors` public listing. No rotation endpoint — beta-stage acceptance per the asker's call. Existing patients grandfathered (their `patient_auth.doctor_id` binding is unchanged).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic, React + antd-mobile.

---

## Risks accepted (for beta rollout)

- 4 chars × 32-symbol alphabet = ~1M combinations. At 100K doctors, random-guess hit rate is 10%. Distributed low-rate brute force across mobile proxies is feasible at scale. **Mitigation:** rate limit + audit + doctor notification + monitor in prod; rotate to 6 or 8 chars (schema headroom is already there) if abuse signal appears.
- No rotation endpoint. WeChat screenshot leak permanently degrades that doctor's posture. **Mitigation:** none until rotation is added in v1.
- Oracle-safety is mandatory: every failure path must return the same response shape and similar timing. Otherwise the entire scheme is bypassed.

---

## File Structure

### Backend — modify

- `src/db/models/doctor.py` — add `patient_attach_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True, unique=True, index=True)` to `Doctor`.
- `src/channels/web/auth/unified.py` — change `unified_register_patient` to take `attach_code` instead of `doctor_id`, with oracle-safe error handling. Drop `list_doctors_for_registration`.
- `src/infra/auth/unified.py` (or wherever `register_patient` lives) — accept attach_code, look up doctor, return doctor_id internally.
- `src/infra/auth/rate_limit.py` (or equivalent existing rate-limit module) — extend to support per-IP scope on `auth.unified.register.patient`.

### Backend — create

- `src/infra/attach_code.py` — small helper module: `ALPHABET` (32 chars), `generate_code(length=4) -> str`, `normalize(code: str) -> str` (uppercase + strip).
- `src/channels/web/doctor_dashboard/attach_code_routes.py` — new router with `GET /api/manage/patient-attach-code` returning `{code, qr_url}`.
- `alembic/versions/<uuid>_patient_attach_code.py` — adds the column + backfills random 4-char codes for every existing doctor (uniqueness guaranteed by retry loop + UNIQUE constraint).

### Frontend — modify

- `frontend/web/src/v2/pages/doctor/settings/...` — add a card showing the attach code in large monospace + QR component + 复制 button. Locate the right settings file via `grep`. (No rotate UI.)
- `frontend/web/src/v2/pages/patient/...` — patient registration form: replace doctor picker with `attach_code` input (4-char field, auto-uppercase, monospace, autofocus). Support `?code=XYZ` URL param pre-fill. Deep-link landing route handles the URL.
- `frontend/web/src/api.js` — add `getDoctorAttachCode(token)`; modify patient register helper to send `attach_code` not `doctor_id`. Drop the public `listDoctorsForRegistration` helper.

### Frontend — possibly create

- `frontend/web/src/v2/components/AttachCodeQR.jsx` — small SVG QR component (use existing `qrcode` lib if present in package.json — search). Falls back to a static `<div>` if no QR lib is available.

### Tests — create

- `tests/core/test_attach_code.py` — generate_code returns 4 uppercase chars from alphabet, normalize handles whitespace + case + ambiguous chars.
- `tests/api/test_patient_register_attach_code.py` — happy path (valid code → 200 with token); oracle parity (invalid code, valid code + duplicate nickname, valid code + missing field all return same status + body shape; timings within 50ms of each other); rate limit fires after 3 failed attempts; the public `/unified/doctors` endpoint is gone.
- `tests/api/test_doctor_attach_code_endpoint.py` — doctor-auth required; returns code + qr_url; same code returned across multiple calls (permanent).

### Test fixture update

- `frontend/web/tests/e2e/fixtures/doctor-auth.ts` — `registerPatient` now fetches the doctor's attach code via the new endpoint and posts it instead of `doctor_id`.

---

## Phase 0 — Backend foundation (independently shippable)

### Task A.1: Schema + ORM column + backfill

**Files:**
- Create: `alembic/versions/<uuid>_patient_attach_code.py`
- Modify: `src/db/models/doctor.py`
- Create: `src/infra/attach_code.py`
- Test: `tests/core/test_attach_code.py`

- [ ] **Step 1: Implement `src/infra/attach_code.py`**

```python
"""Patient attach code — small per-doctor permanent code patients use to bind."""
import secrets

# 32-char alphabet excludes ambiguous: 0/O, 1/I/l
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
DEFAULT_LENGTH = 4


def generate_code(length: int = DEFAULT_LENGTH) -> str:
    """Cryptographically random uppercase code from the unambiguous alphabet."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def normalize(code: str) -> str:
    """User input → canonical form: uppercase, strip whitespace, no hyphens."""
    if not code:
        return ""
    return code.strip().upper().replace("-", "").replace(" ", "")
```

- [ ] **Step 2: Write tests**

```python
# tests/core/test_attach_code.py
import re
from src.infra.attach_code import generate_code, normalize, ALPHABET

def test_generate_code_default_length():
    code = generate_code()
    assert len(code) == 4
    assert all(c in ALPHABET for c in code)

def test_generate_code_custom_length():
    assert len(generate_code(8)) == 8

def test_alphabet_has_no_ambiguous_chars():
    for bad in "01OIlo":
        assert bad not in ALPHABET

def test_normalize_uppercases():
    assert normalize("ab2c") == "AB2C"

def test_normalize_strips_whitespace_and_hyphens():
    assert normalize("  ab-2c ") == "AB2C"

def test_normalize_handles_empty():
    assert normalize("") == ""
    assert normalize(None) == ""

def test_codes_are_unique_with_high_probability():
    codes = {generate_code() for _ in range(1000)}
    assert len(codes) >= 990  # collision rate < 1% at 1000 samples in 1M space
```

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/core/test_attach_code.py -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent`

- [ ] **Step 3: Add ORM column to Doctor**

In `src/db/models/doctor.py`, inside `class Doctor(Base)`:

```python
patient_attach_code: Mapped[Optional[str]] = mapped_column(
    String(8), nullable=True, unique=True, index=True,
)
```

- [ ] **Step 4: Generate Alembic migration**

```bash
ENVIRONMENT=development /Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic revision -m "patient_attach_code"
```

- [ ] **Step 5: Write upgrade with backfill**

```python
"""patient_attach_code

Adds VARCHAR(8) patient_attach_code on doctors with UNIQUE constraint and backfills
a random 4-char code for every existing doctor. Width 8 leaves room to grow to
6 or 8 chars later without a schema change.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import select, update

# Inline the alphabet — migrations should not import application code that may evolve.
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _gen():
    import secrets
    return "".join(secrets.choice(_ALPHABET) for _ in range(4))


def upgrade():
    op.add_column("doctors", sa.Column("patient_attach_code", sa.String(8), nullable=True))
    op.create_index("ix_doctors_patient_attach_code", "doctors", ["patient_attach_code"], unique=True)

    # Backfill existing doctors. Retry on unique-constraint collision.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT doctor_id FROM doctors WHERE patient_attach_code IS NULL")).all()
    used = set(r[0] for r in bind.execute(sa.text("SELECT patient_attach_code FROM doctors WHERE patient_attach_code IS NOT NULL")).all() if r[0])
    for (did,) in rows:
        for _ in range(50):
            code = _gen()
            if code in used:
                continue
            try:
                bind.execute(sa.text("UPDATE doctors SET patient_attach_code = :c WHERE doctor_id = :d"), {"c": code, "d": did})
                used.add(code)
                break
            except Exception:
                continue


def downgrade():
    op.drop_index("ix_doctors_patient_attach_code", table_name="doctors")
    op.drop_column("doctors", "patient_attach_code")
```

- [ ] **Step 6: Apply migration**

```bash
ENVIRONMENT=development /Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/alembic upgrade head
```

Verify: `sqlite3 /tmp/e2e_test.db "SELECT doctor_id, patient_attach_code FROM doctors;"` (or use the dev DB if you prefer) — every row should have a code.

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/*patient_attach_code*.py src/db/models/doctor.py src/infra/attach_code.py tests/core/test_attach_code.py
git commit -m "feat(auth): patient_attach_code column + generator helper"
```

---

### Task A.2: Doctor-side endpoint to fetch the code + QR URL

**Files:**
- Create: `src/channels/web/doctor_dashboard/attach_code_routes.py`
- Modify: wherever doctor_dashboard routers are mounted (`src/channels/web/doctor_dashboard/__init__.py` likely)
- Test: `tests/api/test_doctor_attach_code_endpoint.py`

- [ ] **Step 1: Implement endpoint**

```python
"""Doctor-side endpoint returning the doctor's permanent patient attach code + QR URL."""
import os
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.db.session import get_db
from src.db.models.doctor import Doctor
from src.infra.attach_code import generate_code

router = APIRouter()

# Public domain prefix for QR deep-links. Configurable for prod vs dev.
QR_LINK_BASE = os.environ.get("PATIENT_REGISTER_BASE_URL", "https://patient.doctoragentai.cn")


@router.get("/api/manage/patient-attach-code")
async def get_patient_attach_code(
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    # Reuse existing doctor-auth pattern from neighbor endpoints — search
    # `resolve_doctor_id_from_auth_or_fallback` calls in `src/channels/web/`
    # for the canonical pattern; this is illustrative.
    doctor = (await session.execute(
        select(Doctor).where(Doctor.doctor_id == doctor_id)
    )).scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="doctor not found")

    # Lazy-backfill: if the doctor has no code (e.g., created before migration backfill ran),
    # generate one now with a uniqueness retry. This makes the field effectively NOT NULL
    # for any future read, without requiring a NOT NULL constraint up front.
    if not doctor.patient_attach_code:
        for _ in range(50):
            candidate = generate_code()
            doctor.patient_attach_code = candidate
            try:
                await session.commit()
                break
            except Exception:
                await session.rollback()
                doctor = (await session.execute(
                    select(Doctor).where(Doctor.doctor_id == doctor_id)
                )).scalar_one_or_none()
                if doctor and doctor.patient_attach_code:
                    break

    code = doctor.patient_attach_code
    qr_url = f"{QR_LINK_BASE}/patient/register?code={code}"
    return {"code": code, "qr_url": qr_url}
```

- [ ] **Step 2: Mount router**

In `src/channels/web/doctor_dashboard/__init__.py` (or wherever doctor_dashboard mounting happens), add:

```python
from .attach_code_routes import router as _attach_code_router
# ... in the include_router chain
app_or_parent.include_router(_attach_code_router)
```

- [ ] **Step 3: Write tests**

```python
# tests/api/test_doctor_attach_code_endpoint.py
import pytest
from sqlalchemy import select
from src.db.models.doctor import Doctor
from src.channels.web.doctor_dashboard.attach_code_routes import get_patient_attach_code

@pytest.mark.asyncio
async def test_returns_code_and_qr_url(db_session):
    db_session.add(Doctor(doctor_id="doc_x", name="Dr X", patient_attach_code="AB2C"))
    await db_session.flush()
    result = await get_patient_attach_code(doctor_id="doc_x", authorization=None, session=db_session)
    assert result["code"] == "AB2C"
    assert result["qr_url"].endswith("/patient/register?code=AB2C")

@pytest.mark.asyncio
async def test_returns_same_code_on_repeated_calls(db_session):
    db_session.add(Doctor(doctor_id="doc_y", name="Dr Y", patient_attach_code="XY3Z"))
    await db_session.flush()
    a = await get_patient_attach_code(doctor_id="doc_y", authorization=None, session=db_session)
    b = await get_patient_attach_code(doctor_id="doc_y", authorization=None, session=db_session)
    assert a["code"] == b["code"]

@pytest.mark.asyncio
async def test_lazy_backfill_when_code_missing(db_session):
    db_session.add(Doctor(doctor_id="doc_z", name="Dr Z", patient_attach_code=None))
    await db_session.flush()
    result = await get_patient_attach_code(doctor_id="doc_z", authorization=None, session=db_session)
    assert result["code"] is not None
    assert len(result["code"]) == 4

@pytest.mark.asyncio
async def test_unknown_doctor_returns_404(db_session):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await get_patient_attach_code(doctor_id="ghost", authorization=None, session=db_session)
    assert exc.value.status_code == 404
```

(Adapt fixture pattern to match other tests/api/* files — likely uses `db_session` from `tests/core/conftest.py` like the supplement_handlers tests do.)

- [ ] **Step 4: Run tests + commit**

```bash
git add src/channels/web/doctor_dashboard/attach_code_routes.py src/channels/web/doctor_dashboard/__init__.py tests/api/test_doctor_attach_code_endpoint.py
git commit -m "feat(auth): GET /api/manage/patient-attach-code endpoint"
```

---

### Task A.3: Patient registration switches to attach_code (oracle-safe + rate-limited)

**Files:**
- Modify: `src/channels/web/auth/unified.py`
- Modify: `src/infra/auth/unified.py` (or wherever `register_patient` is implemented)
- Modify: `src/infra/auth/rate_limit.py` (or equivalent)
- Test: `tests/api/test_patient_register_attach_code.py`

- [ ] **Step 1: Update `PatientRegisterRequest`**

In `src/channels/web/auth/unified.py`:

```python
class PatientRegisterRequest(BaseModel):
    nickname: str
    passcode: str
    attach_code: str  # NEW — required; doctor_id REMOVED
    gender: Optional[str] = None
```

- [ ] **Step 2: Rewrite the endpoint with oracle safety**

```python
import asyncio
import time
from src.infra.attach_code import normalize as normalize_attach_code

# Constant duration to enforce on EVERY response — pads short-fail responses
# to roughly the cost of the success path so timing leaks are minimized.
_REGISTER_MIN_LATENCY_S = 0.4


@router.post("/unified/register/patient")
async def unified_register_patient(
    body: PatientRegisterRequest,
    request: Request,
):
    started = time.monotonic()
    # Per-IP rate limit BEFORE any DB work — and the same response is returned
    # whether rate-limited or not, so the attacker cannot tell which.
    enforce_ip_rate_limit(
        request, scope="auth.unified.register.patient",
        max_requests=3, window_seconds=3600,
    )

    code = normalize_attach_code(body.attach_code)
    # Always try the registration. The helper returns None on any failure; we never
    # surface why. The response body is identical for every failure type.
    result = None
    try:
        result = await register_patient_by_attach_code(
            nickname=body.nickname,
            passcode=body.passcode,
            attach_code=code,
            gender=body.gender,
        )
    except Exception:
        result = None

    # Pad to a minimum latency so success vs failure cannot be distinguished by timing.
    elapsed = time.monotonic() - started
    if elapsed < _REGISTER_MIN_LATENCY_S:
        await asyncio.sleep(_REGISTER_MIN_LATENCY_S - elapsed)

    if not result:
        # ORACLE-SAFE: identical detail string for ALL failures.
        raise HTTPException(status_code=422, detail="无法完成注册")
    return result
```

- [ ] **Step 3: Implement `register_patient_by_attach_code`**

Locate the existing `register_patient` helper (probably in `src/infra/auth/unified.py` or similar). Add the new variant alongside it:

```python
async def register_patient_by_attach_code(
    nickname: str,
    passcode: str,
    attach_code: str,
    gender: Optional[str],
):
    """Look up doctor by code, then register the patient under that doctor.
    Returns None on any failure (no detail leaked to caller — the route handler
    decides what error envelope to return).
    """
    if not attach_code or len(attach_code) < 4:
        return None
    async with AsyncSessionLocal() as db:
        doctor = (await db.execute(
            select(Doctor).where(Doctor.patient_attach_code == attach_code)
        )).scalar_one_or_none()
        if not doctor:
            return None
        try:
            return await register_patient(nickname, passcode, doctor.doctor_id, gender)
        except Exception:
            return None
```

The legacy `register_patient(nickname, passcode, doctor_id, gender)` keeps its current signature and is now only invoked internally — the public API surface no longer exposes `doctor_id`.

- [ ] **Step 4: Drop `GET /unified/doctors`**

In `src/channels/web/auth/unified.py`, delete the `list_doctors_for_registration` function and its `@router.get("/unified/doctors")` decorator. Also delete or stop using its frontend caller (`frontend/web/src/api.js` likely has a `listDoctorsForRegistration` helper to remove).

- [ ] **Step 5: Add audit log entries**

Add to `register_patient_by_attach_code`:

```python
from src.infra.audit import safe_create_task, audit
# After the doctor lookup:
safe_create_task(audit(
    "patient", "WRITE",
    resource_type="register_attempt",
    resource_id=attach_code[:2] + "**",  # log a prefix only, never full code
    ok=(doctor is not None),
))
```

(Match the existing audit-call pattern used elsewhere — check `src/channels/web/patient_portal/chat.py` for reference.)

- [ ] **Step 6: Write tests**

```python
# tests/api/test_patient_register_attach_code.py
import pytest
import time
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from src.db.models.doctor import Doctor

# These tests use httpx with ASGITransport against the FastAPI app to exercise
# the real route + middleware (rate limit lives at middleware level).
# Pattern mirrors other tests under tests/api/.

@pytest.mark.asyncio
async def test_happy_path_returns_token(seeded_doctor_with_code):
    """Valid code → 200 with token."""
    # ... setup, then POST with valid attach_code → assert 200 + token in body

@pytest.mark.asyncio
async def test_invalid_code_returns_422_with_generic_detail():
    """Invalid code → 422 with detail '无法完成注册'."""

@pytest.mark.asyncio
async def test_response_shape_identical_across_failure_modes():
    """Invalid code, missing field, duplicate nickname, malformed input all
    return the same status code and body shape."""
    # POST with: invalid attach_code, then valid code + already-used nickname,
    # then valid code + missing passcode. Assert all return 422 with detail='无法完成注册'.

@pytest.mark.asyncio
async def test_response_timing_within_50ms_across_failure_modes():
    """Padding guarantees no timing-based oracle."""
    # Measure invalid-code time vs valid-code-but-other-error time.
    # Both should be >= 0.4s and within 50ms of each other.

@pytest.mark.asyncio
async def test_rate_limit_fires_on_4th_attempt():
    """After 3 attempts in the window, the 4th returns rate-limit error
    (which still has the same response shape)."""

@pytest.mark.asyncio
async def test_unified_doctors_endpoint_is_gone():
    """Public doctor list is dropped."""
    # GET /api/auth/unified/doctors → 404
```

(Implement using whichever httpx + ASGITransport pattern other tests/api/* tests use. The shape-parity and timing tests are the load-bearing ones — these are the oracle defense.)

- [ ] **Step 7: Run + commit**

```bash
git add src/channels/web/auth/unified.py src/infra/auth/unified.py tests/api/test_patient_register_attach_code.py
git commit -m "feat(auth): patient register requires attach_code, oracle-safe responses"
```

---

## Phase 1 — Frontend (depends on Phase 0)

### Task B.1: Doctor settings — show attach code + QR

**Files:**
- Modify: doctor settings page (locate via `rg -ln 'SettingsPage\|settings/index' frontend/web/src/v2/pages/doctor/ 2>&1 | head`)
- Modify: `frontend/web/src/api.js` (add `getDoctorAttachCode(token)`)
- Possibly create: `frontend/web/src/v2/components/AttachCodeQR.jsx` (small QR renderer; check `package.json` for an existing `qrcode` lib first)

- [ ] **Step 1: Add api.js helper**

```js
export async function getDoctorAttachCode(token) {
  return doctorRequest("/api/manage/patient-attach-code", token);
}
```

- [ ] **Step 2: Add a card to the doctor settings page**

```jsx
import { getDoctorAttachCode } from "../../../../api";
import { APP, FONT, RADIUS } from "../../theme";

function PatientAttachCodeCard() {
  const [data, setData] = useState(null);
  useEffect(() => {
    getDoctorAttachCode(token).then(setData);
  }, [token]);

  if (!data) return null;

  const copy = () => navigator.clipboard?.writeText(data.code);

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <span style={styles.label}>我的患者邀请码</span>
        <Button size="small" onClick={copy}>复制</Button>
      </div>
      <div style={styles.codeText}>{data.code}</div>
      <AttachCodeQR url={data.qr_url} />
      <p style={styles.hint}>把这个二维码发给您的患者，他们扫一扫就能在患者端登记。</p>
    </div>
  );
}

const styles = {
  card: { background: APP.surface, borderRadius: RADIUS.lg, margin: "8px 12px", padding: "16px" },
  headerRow: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 },
  label: { fontSize: FONT.md, color: APP.text1, fontWeight: 500 },
  codeText: { fontSize: 36, fontFamily: "monospace", letterSpacing: 4, color: APP.primary, textAlign: "center", padding: "12px 0" },
  hint: { fontSize: FONT.sm, color: APP.text4, marginTop: 12, marginBottom: 0 },
};
```

For `AttachCodeQR` — check `frontend/web/package.json` for `qrcode` or `qrcode.react`. If present, use it. If not, render a simple `<canvas>` using a vendored QR library, or just show the URL as plain text + the code as fallback (functional even if the QR doesn't render).

- [ ] **Step 3: Verify in browser; commit**

```bash
git add frontend/web/src/api.js frontend/web/src/v2/pages/doctor/<settings-file>.jsx frontend/web/src/v2/components/AttachCodeQR.jsx
git commit -m "feat(doctor): patient attach code card on settings page"
```

---

### Task B.2: Patient registration — accept attach code

**Files:**
- Modify: patient registration page (locate under `frontend/web/src/v2/pages/patient/`)
- Modify: `frontend/web/src/api.js` (change `registerPatient` to send `attach_code`; drop `listDoctorsForRegistration`)
- Modify: patient app router (if `?code=XYZ` URL pre-fill needs router changes)

- [ ] **Step 1: Update api.js**

```js
export async function registerPatient({ nickname, passcode, attach_code, gender }) {
  const res = await fetch("/api/auth/unified/register/patient", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nickname, passcode, attach_code, gender }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "无法完成注册");
  }
  return res.json();
}

// REMOVE listDoctorsForRegistration entirely.
```

- [ ] **Step 2: Update the registration form**

Replace the doctor picker with:

```jsx
const [attachCode, setAttachCode] = useState("");
useEffect(() => {
  // Pre-fill from URL: /patient/register?code=XYZ
  const params = new URLSearchParams(window.location.search);
  const c = params.get("code");
  if (c) setAttachCode(c.toUpperCase());
}, []);

<input
  type="text"
  inputMode="text"
  autoCapitalize="characters"
  maxLength={8}  // matches schema; v0 codes are 4 but we allow 8 for future
  pattern="[A-Z0-9]+"
  placeholder="医生提供的 4 位邀请码"
  value={attachCode}
  onChange={(e) => setAttachCode(e.target.value.toUpperCase())}
  style={styles.codeInput}
  required
/>
```

Submit handler sends `attach_code` to the API. Failure shows the generic "无法完成注册" message — never any detail beyond that.

- [ ] **Step 3: Verify in browser**

Two flows:
1. User opens `/patient/register?code=AB2C` → field is pre-filled, they fill nickname/passcode, submit → success
2. User opens `/patient/register` cold → field is empty, they type a code, submit → success

Test the failure path too — wrong code shows generic error, no doctor name leaked.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/api.js frontend/web/src/v2/pages/patient/<register-file>.jsx
git commit -m "feat(patient): registration replaces doctor picker with attach code input"
```

---

### Task B.3: Update e2e test fixture

**Files:**
- Modify: `frontend/web/tests/e2e/fixtures/doctor-auth.ts`

- [ ] **Step 1: Update `registerPatient`**

```ts
export async function registerPatient(
  request: APIRequestContext,
  doctorId: string,  // signature unchanged for compatibility, but value is used to fetch the code first
  opts: { name?: string } = {},
): Promise<TestPatient> {
  // Fetch the doctor's permanent attach code via the new endpoint.
  // The endpoint is doctor-auth in prod, but tests use the dev fallback.
  const codeRes = await request.get(
    `${API_BASE_URL}/api/manage/patient-attach-code?doctor_id=${doctorId}`,
  );
  expect(codeRes.ok(), `attach code fetch failed: ${codeRes.status()}`).toBeTruthy();
  const { code: attach_code } = await codeRes.json();

  const suffix = String(Math.floor(Math.random() * 1e6)).padStart(6, "0");
  const nickname = `pat_${suffix}`;
  const passcode = randomPasscode();

  const res = await request.post(`${API_BASE_URL}/api/auth/unified/register/patient`, {
    data: { nickname, passcode, attach_code, gender: "F" },
  });
  expect(res.ok(), `register patient failed: ${res.status()} ${await res.text()}`).toBeTruthy();
  const body = await res.json();
  return { ... };  // unchanged shape
}
```

- [ ] **Step 2: Run the existing e2e suite to verify no regression**

```bash
cd frontend/web
E2E_BASE_URL=http://127.0.0.1:5174 E2E_API_BASE_URL=http://127.0.0.1:8001 npx playwright test --reporter=list
```

If any spec breaks because of the dropped `/unified/doctors` endpoint or other related changes, note them and fix the test (not the production code).

- [ ] **Step 3: Commit**

```bash
git add frontend/web/tests/e2e/fixtures/doctor-auth.ts
git commit -m "test(e2e): registerPatient fixture uses attach_code instead of doctor_id"
```

---

## Self-Review Checklist

- [ ] Every error path in `unified_register_patient` returns `HTTPException(422, "无法完成注册")` — no other detail strings leak.
- [ ] Response timing is padded to ≥ 400ms regardless of failure mode (verify with the timing test in Task A.3).
- [ ] No code path returns the doctor's name, ID, or any other identifier on failure.
- [ ] Rate limit fires on the 4th attempt within an hour (and the rate-limit response itself uses the same envelope).
- [ ] `GET /api/auth/unified/doctors` returns 404 (verified by Task A.3 test).
- [ ] Frontend pre-fills from URL param + auto-uppercases.
- [ ] Doctor settings shows code + QR; no rotate button anywhere.
- [ ] Existing e2e suite passes after fixture update.

## Out of scope (deliberately deferred)

- Code rotation / regeneration endpoint. Beta-stage acceptance per asker.
- Doctor push notification on every new patient bind. Mentioned in spec but not implemented in v0 plan — add when notification infra is touched next.
- Patient list "新增" badge for 24h. Same — add as a separate small task.
- Source IP region display in patient list. Geo lookup is a separate concern; defer.
