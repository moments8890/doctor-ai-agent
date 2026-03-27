# QR Code Login — Design Spec

> **Features:** D6.1 (QR Code Generator), P1.1 (QR Code Entry)
> **Scope:** Admin generates doctor QR, doctor generates patient QR. QR encodes a long-lived JWT URL that lands the user directly in the app.
> **Date:** 2026-03-26

---

## 1. Architecture

A QR code is a URL containing a JWT token. Scanning it opens the app, which reads the token from URL params, stores it in localStorage, and lands the user on their main page — no login page involved.

**Three flows:**
1. **Admin → Doctor QR**: admin panel generates a QR for a specific doctor
2. **Doctor → Own QR**: doctor settings page shows their own QR for self-login on other devices
3. **Doctor → Patient QR**: PatientDetail page generates a QR for a specific patient

**Token:** Standard JWT with 30-day expiry. Contains `{role, doctor_id, patient_id, name}`. Deterministically maps to one user. Regeneratable — doctor taps button, gets new QR, same person.

**No new tables.** Reuses existing `issue_token()` from `src/infra/auth/unified.py`. No one-time-use tracking — early release simplicity.

---

## 2. Backend

### 2.1 New Endpoint: `POST /api/auth/qr-token`

Generates a long-lived JWT for QR code use.

**Request:**
```json
{
  "role": "doctor" | "patient",
  "doctor_id": "string",
  "patient_id": 13          // required when role=patient
}
```

**Response:**
```json
{
  "token": "eyJhbG...",
  "url": "https://app.com/doctor?token=eyJhbG...&doctor_id=xxx&name=xxx",
  "expires_in_days": 30
}
```

**Logic:**
1. Validate the doctor_id exists in the doctors table
2. If `role=patient`, validate patient_id exists and belongs to doctor_id
3. Call `issue_token()` with 30-day expiry, `role`, `doctor_id`, `patient_id`, `name`
4. Build URL: base URL + role path + query params (`token`, `doctor_id`, `name`)
5. Return token + full URL

**Auth:** This endpoint requires admin auth (for doctor QR) or doctor auth (for patient QR). Check `Authorization` header.

**Base URL:** Read from env var `APP_BASE_URL` (default: `http://localhost:5173` in dev).

### 2.2 URL Format

**Doctor QR URL:**
```
{APP_BASE_URL}/doctor?token={jwt}&doctor_id={id}&name={name}
```

**Patient QR URL:**
```
{APP_BASE_URL}/patient?token={jwt}&doctor_id={id}&name={name}
```

App.jsx already handles `?token=&doctor_id=&name=` params — it calls `setAuth()` and removes the params from the URL.

### 2.3 Patient Portal Token Handling

PatientPage.jsx currently reads its token from `localStorage["patient_portal_token"]`, not from URL params. Need to add URL param handling in PatientPage similar to what App.jsx does for doctor auth:
- Read `token`, `doctor_id`, `name` from URL params
- If present, store in localStorage and clear URL params
- Continue with normal authenticated flow

---

## 3. Frontend

### 3.1 QR Code Library

Install `qrcode.react` — lightweight React component that renders QR codes as SVG.

```bash
cd frontend/web && npm install qrcode.react
```

### 3.2 QRDialog Component

New shared component: `frontend/web/src/components/QRDialog.jsx`

Uses `SheetDialog` as shell. Shows:
- Title: "扫码登录" or "患者二维码"
- QR code image (rendered by `qrcode.react`)
- Name of the person this QR is for
- Expiry info: "有效期30天"
- "重新生成" button to regenerate

```
┌──────────────────────────────────────┐
│         患者二维码                    │
│                                      │
│         ┌──────────┐                 │
│         │ ██ ██ ██ │                 │
│         │ ██    ██ │                 │
│         │ ██ ██ ██ │                 │
│         └──────────┘                 │
│                                      │
│         李复诊                        │
│         有效期30天                    │
│                                      │
│     [重新生成]                        │
└──────────────────────────────────────┘
```

**Props:** `open`, `onClose`, `title`, `name`, `url`, `loading`, `onRegenerate`

**Reused components:** SheetDialog, AppButton

### 3.3 Admin Page — Doctor QR

Add a "二维码" action button per doctor row in the admin panel. Clicking it:
1. Calls `POST /api/auth/qr-token` with `{role: "doctor", doctor_id: "xxx"}`
2. Opens QRDialog with the returned URL

### 3.4 Doctor Settings — Own QR

Add a "我的二维码" row in the Settings page under "工具" section (alongside 报告模板, 知识库). Uses `SettingsRow` with a QR icon. Clicking it:
1. Calls `POST /api/auth/qr-token` with `{role: "doctor", doctor_id: current_doctor_id}`
2. Opens QRDialog with title "我的二维码" and the doctor's name
3. Use case: doctor scans on another device to log in there

### 3.5 PatientDetail — Patient QR

Add a "二维码" button in the PatientDetail expanded profile actions (alongside 删除/导出). Clicking it:
1. Calls `POST /api/auth/qr-token` with `{role: "patient", doctor_id: "xxx", patient_id: 13}`
2. Opens QRDialog with the returned URL

### 3.6 PatientPage — URL Param Handling

Add token absorption from URL params in PatientPage.jsx (mirrors App.jsx pattern):

```jsx
useState(() => {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  const did = params.get("doctor_id");
  const name = params.get("name");
  if (token) {
    localStorage.setItem("patient_portal_token", token);
    if (name) localStorage.setItem("patient_portal_name", name);
    if (did) localStorage.setItem("patient_portal_doctor_id", did);
    // Clean URL
    const url = new URL(window.location.href);
    ["token", "doctor_id", "name"].forEach(k => url.searchParams.delete(k));
    window.history.replaceState({}, "", url.toString());
  }
});
```

---

## 4. Component Reuse

| Component | Usage |
|-----------|-------|
| `SheetDialog` | QRDialog shell |
| `AppButton` | Regenerate button |
| `issue_token()` | Backend JWT generation (existing) |
| App.jsx URL param absorption | Pattern for PatientPage token handling |

| New Component | Purpose |
|---------------|---------|
| `QRDialog` | Shared QR display dialog (~40 lines) |

| New Dependency | Purpose |
|----------------|---------|
| `qrcode.react` | QR code SVG rendering |

---

## 5. Data Flow

```
Admin/Doctor taps "二维码"
    │
    ▼
Frontend calls POST /api/auth/qr-token {role, doctor_id, patient_id?}
    │
    ▼
Backend validates user exists → issue_token(30 days) → builds URL
    │
    ▼
Frontend receives {token, url} → renders QR code in QRDialog
    │
    ▼
User scans QR with phone camera → opens URL in browser
    │
    ▼
App reads ?token=&doctor_id=&name= from URL params
    │
    ▼
Stores in localStorage → clears URL params → lands on main page
    │
    ▼
User is logged in for 30 days. If lost, regenerate QR (2 seconds).
```

---

## 6. Security (Early Release)

- **30-day JWT expiry** — acceptable for small trusted user base
- **No one-time-use** — multiple scans OK, simpler implementation
- **No revocation** — if compromised, wait for expiry or change secret key
- **QR shown on screen** — not printed publicly, doctor controls sharing
- **Admin auth required** for doctor QR generation
- **Doctor auth required** for patient QR generation
- **Patient data access** scoped to the specific patient_id in the token

---

## 7. Design System Compliance

- [x] QRDialog uses SheetDialog + AppButton (existing components)
- [x] Chinese-first labels ("扫码登录", "患者二维码", "重新生成", "有效期30天")
- [x] Flat design, no shadows
- [x] TYPE/COLOR tokens from theme.js
