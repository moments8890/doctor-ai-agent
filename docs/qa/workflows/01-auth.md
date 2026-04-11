# Workflow 01 — Auth (login / logout / history safety)

Ship gate for doctor authentication. Covers the first and last thing a
doctor does in the app: logging in, logging out, and the browser-back
safety check that prevents post-logout navigation to authenticated pages.

**Area:** `/login`, `src/pages/LoginPage.jsx`, `SettingsPage.jsx` logout
handler, `src/store/doctorStore.js`
**Spec:** `frontend/web/tests/e2e/01-auth.spec.ts`
**Estimated runtime:** ~3 min manual / ~15 s automated

---

## Scope

**In scope**

- Doctor login with phone + birth-year passcode.
- Bottom-nav render after successful login (4 tabs visible).
- Logout path from settings.
- Browser back-button after logout (BUG-07 regression gate).
- Invalid credential rejection — error toast, no navigation.
- Token persistence across full-page reload.

**Out of scope**

- Patient-side login (patient portal has its own entrypoint).
- First-time doctor onboarding wizard — see [02-onboarding](02-onboarding.md).
- Password/passcode reset (not shipped yet).
- WeChat SSO / QR login (tracked separately).

---

## Pre-flight

Standard pre-flight from [`README.md`](README.md#shared-pre-flight). This
workflow uses only the `doctorAuth` fixture — no additional seeding. The
fixture registers a fresh doctor each run so there is no phone-collision
risk on re-runs.

---

## Steps

### 1. Login

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/login` in a clean session (no localStorage) | Page renders with "医生" / "患者" tab toggle; 医生 tab selected by default |
| 1.2 | Enter `昵称` = registered phone (e.g. 13800138001) | Field accepts full 11-digit value |
| 1.3 | Enter `口令` = birth year as integer (e.g. 1980) | Field accepts 4-digit numeric value |
| 1.4 | Tap `登录` | Within 2 s: redirected to `/doctor` OR `/doctor/my-ai`; 4-tab bottom nav visible: 我的AI / 患者 / 审核 / 任务 |
| 1.5 | Inspect `localStorage` after login | Contains `doctor-session` key with JSON blob `{state:{doctorId, doctorName, accessToken}, version:0}` (zustand persist shape from `doctorStore.js:13`). In DEV_MODE the app also reads `unified_auth_doctor_id / _token / _name` as a fallback — belt-and-braces |
| 1.6 | Full-page reload (Cmd-R) | App restores to the same tab; no redirect back to `/login`; no flicker of login page |

### 2. Invalid credentials

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Navigate to `/login` | Login form visible |
| 2.2 | Enter correct phone but wrong passcode (e.g. 9999) → 登录 | Error message / toast shown; stays on `/login`; no tokens written to localStorage |
| 2.3 | Enter non-existent phone → 登录 | Same as 2.2 — error shown, no navigation |
| 2.4 | Enter empty fields → 登录 | Button disabled OR client-side validation blocks submit |

### 3. Logout

| # | Action | Verify |
|---|--------|--------|
| 3.1 | From authed state, navigate to Settings (tab: 我的AI → bottom sheet or settings route) | Settings list visible; 退出登录 row in red at the bottom |
| 3.2 | Tap `退出登录` | Either fires immediately OR shows a confirm dialog (cancel LEFT grey / confirm RIGHT red) |
| 3.3 | (If confirm dialog) Tap `退出` | Session cleared; redirected to `/login` |
| 3.4 | Inspect `localStorage` after logout | Either `doctor-session` blob is removed, or the inner `state.accessToken` / `state.doctorId` are null. `clearAuth()` in `doctorStore.js:11` sets them to null — zustand persist writes the blob back with null fields |

### 4. Browser-back safety (BUG-07 regression)

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Log in → navigate to 设置 → log out | Lands on `/login` |
| 4.2 | Press browser back button | Lands on `/login` — **NOT** the old authed settings page |
| 4.3 | Press forward then back a few times | Always lands on `/login` or patient portal; never shows doctor data |

This was the bug fix for BUG-07; the `navigate('/login', {replace:true})`
call should clear history so the authed route is no longer in the stack.

---

## Edge cases

- **Expired token** — if the `accessToken` inside the
  `localStorage["doctor-session"]` blob is stale, the first authed API call
  returns 401 and the app should redirect to `/login`.
  Not automated (requires manipulating server-side token TTL); manual spot
  check when the token expiry logic changes.
- **Trailing whitespace in phone** — the form should strip it, not reject.
- **Resize to desktop (>=1280px) during login** — layout should adapt;
  no overflow or clipped fields.
- **Double-tap 登录** — spec should debounce; two requests not fired.

---

## Known issues

See `docs/qa/hero-path-qa-plan.md` §Known Issues. Auth-related entries:

- **BUG-07** — ✅ Fixed `795729ff`. Browser-back after logout used to show
  the settings page because React Router didn't clear history. Regression
  gate: step 4.2 must land on `/login`.
- **BUG-02** — ✅ Fixed `795729ff`. Doctor named "测试医生" used to render
  as "测试医生医生" in the header. Regression gate: after 1.4 the header
  should show the raw doctor name once, not twice.

---

## Failure modes & debug tips

- **Step 1.4 times out** — likely backend isn't running or `NO_PROXY=*`
  is missing. Check `curl http://127.0.0.1:8000/api/health`.
- **Step 1.5 shows empty localStorage** — the frontend login handler may
  have swallowed the API response. Check the network tab for the POST
  to `/api/auth/unified/login` and verify the 200 body includes `token`.
- **Step 4.2 lands on settings, not `/login`** — BUG-07 regressed;
  inspect `navigate('/login')` call in the logout handler — it must pass
  `{ replace: true }`.
- **Spec flake on 1.1** — if a previous test left tokens behind, add
  `await page.context().clearCookies()` + `localStorage.clear()` before
  the goto.
