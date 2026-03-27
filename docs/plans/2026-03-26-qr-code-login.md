# QR Code Login — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate QR codes that let doctors and patients scan-to-login directly into the app without going through the login page.

**Architecture:** One backend endpoint (`POST /api/auth/qr-token`) generates a 30-day JWT and builds a URL. Frontend renders the QR using `qrcode.react` in a `QRDialog` component. Three UI integration points: admin panel (doctor QR), doctor settings (own QR), PatientDetail (patient QR). PatientPage gets URL param token absorption to match App.jsx's existing pattern.

**Tech Stack:** Python/FastAPI (backend), React/MUI + `qrcode.react` (frontend), existing `issue_token()` with custom TTL

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/infra/auth/unified.py` | Modify | Add `ttl_seconds` parameter to `issue_token()` |
| `src/channels/web/unified_auth_routes.py` | Modify | Add `POST /api/auth/qr-token` endpoint |
| `frontend/web/src/components/QRDialog.jsx` | Create | Shared QR display dialog |
| `frontend/web/src/api.js` | Modify | Add `generateQRToken()` API function |
| `frontend/web/src/pages/doctor/subpages/SettingsListSubpage.jsx` | Modify | Add "我的二维码" row |
| `frontend/web/src/pages/doctor/patients/PatientDetail.jsx` | Modify | Add "二维码" action in PatientActionBar |
| `frontend/web/src/pages/admin/AdminPage.jsx` | Modify | Add "二维码" action per doctor row |
| `frontend/web/src/pages/patient/PatientPage.jsx` | Modify | Add URL param token absorption |

---

### Task 1: Backend — Add TTL parameter to issue_token

**Files:**
- Modify: `src/infra/auth/unified.py:32-54`

- [ ] **Step 1: Read the current function**

Open `src/infra/auth/unified.py` and find `issue_token()` at line 32. It currently uses `_TOKEN_TTL` (7 days) hardcoded from env var. We need to allow callers to pass a custom TTL.

- [ ] **Step 2: Add optional ttl_seconds parameter**

Add a `ttl_seconds` parameter with default `None` (falls back to existing `_TOKEN_TTL`):

```python
def issue_token(
    role: str,
    doctor_id: Optional[str] = None,
    patient_id: Optional[int] = None,
    name: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
) -> str:
```

In the body, change the expiry line from:
```python
"exp": now + _TOKEN_TTL,
```
to:
```python
"exp": now + (ttl_seconds if ttl_seconds is not None else _TOKEN_TTL),
```

- [ ] **Step 3: Commit**

```bash
git add src/infra/auth/unified.py
git commit -m "feat: add ttl_seconds parameter to issue_token for QR code tokens"
```

---

### Task 2: Backend — Add QR token endpoint

**Files:**
- Modify: `src/channels/web/unified_auth_routes.py`
- Reference: `src/infra/auth/unified.py` (`issue_token`), `src/db/models/doctor.py`, `src/db/models/patient.py`

- [ ] **Step 1: Read the existing routes file**

Open `src/channels/web/unified_auth_routes.py`. Note the router variable (`router`), prefix (`/api/auth`), and how other endpoints handle auth. Find how `AsyncSessionLocal` and models are imported — follow the same pattern.

- [ ] **Step 2: Add the QR token endpoint**

Add a new endpoint at the end of the file:

```python
class QRTokenRequest(BaseModel):
    role: str  # "doctor" or "patient"
    doctor_id: str
    patient_id: Optional[int] = None

class QRTokenResponse(BaseModel):
    token: str
    url: str
    expires_in_days: int

@router.post("/qr-token", response_model=QRTokenResponse)
async def generate_qr_token(
    body: QRTokenRequest,
    authorization: Optional[str] = Header(default=None),
):
    """Generate a long-lived JWT token for QR code login.

    Auth: caller must be an authenticated doctor (for own QR or patient QR).
    The caller's doctor_id from JWT must match body.doctor_id — doctors can
    only generate QRs for themselves and their own patients.
    Note: QR tokens intentionally bypass access-code verification (early release).
    """
    import os
    from db.engine import AsyncSessionLocal
    from db.models.doctor import Doctor

    if body.role not in ("doctor", "patient"):
        raise HTTPException(status_code=422, detail="role must be 'doctor' or 'patient'")

    # Auth: verify caller is the doctor they claim to be
    # For early release: doctor auth required. Admin bypasses via X-Admin-Token handled separately.
    caller = await authenticate(authorization)
    if caller.doctor_id != body.doctor_id:
        raise HTTPException(status_code=403, detail="Can only generate QR for your own account or your patients")

    # Validate doctor exists
    async with AsyncSessionLocal() as db:
        doctor = await db.get(Doctor, body.doctor_id)
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")
        doctor_name = doctor.name or body.doctor_id

        patient_name = None
        patient_id = None
        if body.role == "patient":
            if body.patient_id is None:
                raise HTTPException(status_code=422, detail="patient_id required for patient QR")
            from db.models.patient import Patient
            patient = await db.get(Patient, body.patient_id)
            if not patient or patient.doctor_id != body.doctor_id:
                raise HTTPException(status_code=404, detail="Patient not found for this doctor")
            patient_name = patient.name
            patient_id = patient.id

    # Issue 30-day token
    ttl_30_days = 30 * 24 * 3600
    token = issue_token(
        role=body.role,
        doctor_id=body.doctor_id,
        patient_id=patient_id,
        name=patient_name if body.role == "patient" else doctor_name,
        ttl_seconds=ttl_30_days,
    )

    # Build URL
    base_url = os.environ.get("APP_BASE_URL", "http://localhost:5173")
    path = "/patient" if body.role == "patient" else "/doctor"
    name_for_url = patient_name if body.role == "patient" else doctor_name
    from urllib.parse import urlencode
    params = urlencode({"token": token, "doctor_id": body.doctor_id, "name": name_for_url or ""})
    url = f"{base_url}{path}?{params}"

    return QRTokenResponse(token=token, url=url, expires_in_days=30)
```

Make sure `issue_token` is imported at the top (it likely already is — check existing imports). Add `Optional` and `Header` imports if missing.

- [ ] **Step 3: Check Patient model import path**

The Patient model may be at `db.models.patients` or `db.models.patient`. Read `src/db/models/` to find the exact file name. Use the correct import path.

- [ ] **Step 4: Commit**

```bash
git add src/channels/web/unified_auth_routes.py
git commit -m "feat: add POST /api/auth/qr-token endpoint for QR code login"
```

---

### Task 3: Frontend — Install qrcode.react and create QRDialog

**Files:**
- Create: `frontend/web/src/components/QRDialog.jsx`

- [ ] **Step 1: Install dependency**

```bash
cd frontend/web && npm install qrcode.react
```

- [ ] **Step 2: Create QRDialog component**

```jsx
import { Box, CircularProgress, Typography } from "@mui/material";
import { QRCodeSVG } from "qrcode.react";
import SheetDialog from "./SheetDialog";
import AppButton from "./AppButton";
import { TYPE, COLOR } from "../theme";

export default function QRDialog({ open, onClose, title, name, url, loading, error, onRegenerate }) {
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title={title || "二维码"}
      desktopMaxWidth={360}
      footer={
        <AppButton variant="secondary" size="md" fullWidth onClick={onRegenerate} disabled={loading}>
          重新生成
        </AppButton>
      }
    >
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 2 }}>
        {loading ? (
          <Box sx={{ py: 4 }}><CircularProgress size={24} /></Box>
        ) : error ? (
          <Typography sx={{ py: 4, fontSize: TYPE.body.fontSize, color: COLOR.danger, textAlign: "center" }}>
            {error}
          </Typography>
        ) : url ? (
          <Box sx={{ p: 2, bgcolor: COLOR.white, borderRadius: "8px", border: `1px solid ${COLOR.borderLight}` }}>
            <QRCodeSVG value={url} size={200} level="M" />
          </Box>
        ) : null}
        {name && !error && (
          <Typography sx={{ mt: 1.5, fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.text1 }}>
            {name}
          </Typography>
        )}
        {!error && (
          <Typography sx={{ mt: 0.5, fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
            有效期30天
          </Typography>
        )}
      </Box>
    </SheetDialog>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/components/QRDialog.jsx frontend/web/package.json frontend/web/package-lock.json
git commit -m "feat: add QRDialog component with qrcode.react"
```

---

### Task 4: Frontend — Add generateQRToken API function

**Files:**
- Modify: `frontend/web/src/api.js`

- [ ] **Step 1: Add the API function**

Find the auth-related functions section in `api.js` (around line 126). Add:

Follow the existing pattern in api.js — use `apiUrl()` for URL construction and include the Bearer token. Find how other authenticated doctor endpoints work (e.g., `getDoctorProfile`) and follow the same pattern:

```javascript
export async function generateQRToken(role, doctorId, patientId) {
  const res = await fetch(apiUrl("/api/auth/qr-token"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      role,
      doctor_id: doctorId,
      ...(patientId != null && { patient_id: patientId }),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "二维码生成失败");
  }
  return res.json();
}
```

IMPORTANT: Check how `apiUrl()` and `authHeaders()` (or equivalent) are defined in this file. The exact function names may differ — read the top of api.js to find the URL builder and auth header helper. Use whatever pattern other authenticated endpoints use.

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/api.js
git commit -m "feat: add generateQRToken API function"
```

---

### Task 5: Frontend — Add "我的二维码" to doctor Settings

**Files:**
- Modify: `frontend/web/src/pages/doctor/subpages/SettingsListSubpage.jsx` (~line 96-102)

- [ ] **Step 1: Read the current settings rows**

Open `SettingsListSubpage.jsx` and find the "工具" section (~line 96). It has two `SettingsRow` components: 报告模板 and 知识库.

- [ ] **Step 2: Add QR code row and state**

Add a QR icon import at the top:
```jsx
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
```

Add a new `SettingsRow` after the 知识库 row:
```jsx
<SettingsRow icon={<QrCode2OutlinedIcon sx={{ color: "#e8833a", fontSize: ICON.lg }} />}
  label="我的二维码" sublabel="扫码登录其他设备" onClick={onQRCode} />
```

Add `onQRCode` to the component's props and pass it from the parent.

- [ ] **Step 3: Add QR dialog state in SettingsPage**

In `SettingsPage.jsx` (or wherever `SettingsListSubpage` is rendered), add state and handler:

```jsx
import QRDialog from "../../components/QRDialog";
import { generateQRToken } from "../../api";

const [qrOpen, setQrOpen] = useState(false);
const [qrUrl, setQrUrl] = useState("");
const [qrError, setQrError] = useState("");
const [qrLoading, setQrLoading] = useState(false);

async function handleGenerateQR() {
  setQrLoading(true);
  setQrError("");
  setQrOpen(true);
  try {
    const data = await generateQRToken("doctor", doctorId);
    setQrUrl(data.url);
  } catch (e) {
    setQrUrl("");
    setQrError(e.message || "生成失败");
  } finally {
    setQrLoading(false);
  }
}
```

Pass `onQRCode={() => handleGenerateQR()}` to `SettingsListSubpage`.

Render the dialog:
```jsx
<QRDialog
  open={qrOpen}
  onClose={() => setQrOpen(false)}
  title="我的二维码"
  name={doctorName || doctorId}
  url={qrUrl}
  loading={qrLoading}
  error={qrError}
  onRegenerate={handleGenerateQR}
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/doctor/subpages/SettingsListSubpage.jsx frontend/web/src/pages/doctor/SettingsPage.jsx
git commit -m "feat: add '我的二维码' to doctor settings page"
```

---

### Task 6: Frontend — Add "二维码" to PatientDetail actions

**Files:**
- Modify: `frontend/web/src/pages/doctor/patients/PatientDetail.jsx` (~lines 77-97, PatientActionBar)

- [ ] **Step 1: Read PatientActionBar**

Open PatientDetail.jsx and find `PatientActionBar` (line 77). It has three actions: 删除患者, 导出PDF, 门诊报告.

- [ ] **Step 2: Add QR code action**

Add a QR icon import:
```jsx
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
```

Add a new action in `PatientActionBar` between the spacer (`<Box sx={{ flex: 1 }} />`) and the export buttons:

```jsx
<Box onClick={onQRCode}
  sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer", color: "#e8833a", fontSize: TYPE.secondary.fontSize, "&:active": { opacity: 0.6 } }}>
  <QrCode2OutlinedIcon sx={{ fontSize: ICON.sm }} />
  二维码
</Box>
```

Add `onQRCode` to `PatientActionBar`'s props.

- [ ] **Step 3: Add QR dialog state in PatientDetail**

In the parent component that renders `PatientActionBar`, add state:

```jsx
import QRDialog from "../../../components/QRDialog";
import { generateQRToken } from "../../../api";

const [qrOpen, setQrOpen] = useState(false);
const [qrUrl, setQrUrl] = useState("");
const [qrLoading, setQrLoading] = useState(false);

async function handlePatientQR() {
  setQrLoading(true);
  setQrOpen(true);
  try {
    const data = await generateQRToken("patient", doctorId, patient.id);
    setQrUrl(data.url);
  } catch (e) {
    setQrUrl("");
  } finally {
    setQrLoading(false);
  }
}
```

Pass `onQRCode={handlePatientQR}` to `PatientActionBar`.

Render the dialog:
```jsx
<QRDialog
  open={qrOpen}
  onClose={() => setQrOpen(false)}
  title="患者二维码"
  name={patient.name}
  url={qrUrl}
  loading={qrLoading}
  onRegenerate={handlePatientQR}
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/doctor/patients/PatientDetail.jsx
git commit -m "feat: add patient QR code generation in PatientDetail"
```

---

### Task 7: Frontend — Add "二维码" to Admin doctor list

**Files:**
- Modify: `frontend/web/src/pages/admin/AdminPage.jsx`

- [ ] **Step 1: Read the admin doctor table**

Open AdminPage.jsx and find how doctor rows are rendered (~lines 1400-1510). Look for the action buttons per row (copy, view).

- [ ] **Step 2: Add QR code action button**

Add a QR icon button alongside the existing row actions:

```jsx
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
```

Add an `IconButton` or clickable Box next to the existing row action icons. IMPORTANT: gate this on the active table being "doctors" — the action cell is shared by all tables:

```jsx
{activeTable === "doctors" && (
  <IconButton size="small" onClick={(e) => { e.stopPropagation(); handleAdminQR(row.doctor_id, row.name); }}>
    <QrCode2OutlinedIcon sx={{ fontSize: 18 }} />
  </IconButton>
)}
```

Check what variable name the admin page uses for the current table (it may be `activeTable`, `section`, `currentTable`, etc.). Read the code and use the correct name.

- [ ] **Step 3: Add QR dialog state in AdminPage**

```jsx
import QRDialog from "../../components/QRDialog";
import { generateQRToken } from "../../api";

const [adminQrOpen, setAdminQrOpen] = useState(false);
const [adminQrUrl, setAdminQrUrl] = useState("");
const [adminQrName, setAdminQrName] = useState("");
const [adminQrLoading, setAdminQrLoading] = useState(false);

async function handleAdminQR(doctorId, doctorName) {
  setAdminQrLoading(true);
  setAdminQrName(doctorName || doctorId);
  setAdminQrOpen(true);
  try {
    const data = await generateQRToken("doctor", doctorId);
    setAdminQrUrl(data.url);
  } catch (e) {
    setAdminQrUrl("");
  } finally {
    setAdminQrLoading(false);
  }
}
```

Render the dialog at the end of AdminPage:
```jsx
<QRDialog
  open={adminQrOpen}
  onClose={() => setAdminQrOpen(false)}
  title="医生二维码"
  name={adminQrName}
  url={adminQrUrl}
  loading={adminQrLoading}
  onRegenerate={() => handleAdminQR(/* need to store doctorId */)}
/>
```

Note: you'll need to store the `doctorId` for regeneration — add a `adminQrDoctorId` state or combine into an object.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/pages/admin/AdminPage.jsx
git commit -m "feat: add doctor QR code generation in admin panel"
```

---

### Task 8: Frontend — Add URL param token absorption in PatientPage

**Files:**
- Modify: `frontend/web/src/pages/patient/PatientPage.jsx`

- [ ] **Step 1: Find the component init**

Open PatientPage.jsx and find the root `PatientPage` component function (~line 1010). Find where localStorage keys are defined (lines 77-80) and where state is initialized.

- [ ] **Step 2: Add token absorption from URL params**

Add a `useState` initializer (same pattern as App.jsx lines 81-93) near the top of the component, before other effects:

```jsx
useState(() => {
  const params = new URLSearchParams(window.location.search);
  const qrToken = params.get("token");
  const qrDoctorId = params.get("doctor_id");
  const qrName = params.get("name");
  if (qrToken) {
    localStorage.setItem(STORAGE_KEY, qrToken);
    if (qrName) localStorage.setItem(STORAGE_NAME_KEY, qrName);
    if (qrDoctorId) localStorage.setItem(STORAGE_DOCTOR_KEY, qrDoctorId);
    // Clean URL params
    const cleanUrl = new URL(window.location.href);
    ["token", "doctor_id", "name"].forEach(k => cleanUrl.searchParams.delete(k));
    window.history.replaceState({}, "", cleanUrl.toString());
    // Update state if already initialized
    setToken(qrToken);
    if (qrName) setPatientName(qrName);
    if (qrDoctorId) setDoctorId(qrDoctorId);
  }
});
```

CRITICAL: This must run BEFORE the existing `useState` calls that read from localStorage. The pattern is: write URL params to localStorage first, then the existing state initializers (`useState(() => localStorage.getItem(STORAGE_KEY))`) will pick them up naturally.

Place this block as the VERY FIRST `useState` in the PatientPage component, before `const [token, setToken] = useState(...)`:

```jsx
// QR code token absorption — must run before state initialization
useState(() => {
  const params = new URLSearchParams(window.location.search);
  const qrToken = params.get("token");
  if (qrToken) {
    const qrDoctorId = params.get("doctor_id");
    const qrName = params.get("name");
    localStorage.setItem(STORAGE_KEY, qrToken);
    if (qrName) localStorage.setItem(STORAGE_NAME_KEY, qrName);
    if (qrDoctorId) localStorage.setItem(STORAGE_DOCTOR_KEY, qrDoctorId);
    // Clean URL params
    const cleanUrl = new URL(window.location.href);
    ["token", "doctor_id", "name"].forEach(k => cleanUrl.searchParams.delete(k));
    window.history.replaceState({}, "", cleanUrl.toString());
  }
});
```

Do NOT call any state setters inside this block — they don't exist yet. Just write to localStorage. The existing `useState(() => localStorage.getItem(STORAGE_KEY) || "")` calls that follow will read the values we just wrote.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/pages/patient/PatientPage.jsx
git commit -m "feat: add QR token absorption from URL params in PatientPage"
```

---

### Task 9: Verify end-to-end

- [ ] **Step 1: Test backend endpoint**

```bash
curl -s -X POST http://localhost:8000/api/auth/qr-token \
  -H "Content-Type: application/json" \
  -d '{"role":"doctor","doctor_id":"test_doctor"}' | python3 -m json.tool
```

Verify response has `token`, `url` (with query params), and `expires_in_days: 30`.

```bash
curl -s -X POST http://localhost:8000/api/auth/qr-token \
  -H "Content-Type: application/json" \
  -d '{"role":"patient","doctor_id":"test_doctor","patient_id":13}' | python3 -m json.tool
```

Verify patient URL points to `/patient?token=...`.

- [ ] **Step 2: Test doctor settings QR**

1. Navigate to `http://localhost:5173/doctor/settings`
2. Verify "我的二维码" row appears under 工具
3. Click it → QRDialog opens with QR code
4. Verify QR code renders (SVG with squares)
5. Verify name and "有效期30天" shown

- [ ] **Step 3: Test patient QR from PatientDetail**

1. Navigate to a patient detail page
2. Expand the profile
3. Verify "二维码" action appears alongside 删除/导出
4. Click it → QRDialog opens with patient QR
5. Verify title says "患者二维码" and patient name shown

- [ ] **Step 4: Test QR URL absorption**

Open the URL from the QR token response directly in the browser:
1. Doctor URL → should land on doctor workbench (auto-authenticated)
2. Patient URL → should land on patient portal (auto-authenticated)

- [ ] **Step 5: Final commit if fixes needed**

```bash
git add -A
git commit -m "fix: address edge cases in QR code flow"
```
