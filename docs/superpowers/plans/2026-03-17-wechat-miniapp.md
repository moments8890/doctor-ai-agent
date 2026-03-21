# WeChat Mini App (Thin WebView Shell) Implementation Plan

> **Status: ⚠️ PARTIAL** — core implementation done, refinements remain.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt the existing Mini App (`frontend/miniprogram/`) and React web app (`frontend/web/`) so the Mini App acts as a thin WebView shell with silent `wx.login()` auth, invite code fallback via `wxmini_` prefix detection, and proper error/expiry handling.

**Architecture:** The Mini App shell authenticates via `wx.login()` → `/api/auth/wechat-mini/login`, detects stub `wxmini_` doctors, and loads the React app in a `<web-view>`. The React app detects the Mini App environment via `window.__wxjs_environment` and handles 401 expiry gracefully. Zero backend changes.

**Tech Stack:** WeChat Mini App (WXML/WXSS/JS), React 19, Zustand, Material-UI, Vite

**Spec:** `docs/superpowers/specs/2026-03-17-wechat-miniapp-design.md`

**Key discovery:** `frontend/miniprogram/` already has a working login page (invite code + WeChat), a WebView doctor page with token handoff, subscription message support, and a postMessage logout handler. The plan adapts this existing code rather than building from scratch.

**Deviations from spec:**
1. The spec proposes `frontend/miniapp/pages/auth/` and `pages/main/`. The existing codebase already has `frontend/miniprogram/pages/login/` and `pages/doctor/` with the same responsibilities. This plan adapts those existing pages in place rather than creating duplicates. The spec's `frontend/miniapp/` directory name maps to the existing `frontend/miniprogram/`.
2. The spec mentions collecting `specialty` in the invite code form. The backend's `InviteLoginInput.specialty` is optional (`Optional[str] = None`). The existing Mini App login page does not collect specialty, and adding an extra form field slows down the login flow. Specialty can be set later via the doctor profile page (`/api/auth/me` PATCH). Omitted from this plan.

---

## File Map

### Mini App (existing `frontend/miniprogram/`)

| File | Action | Responsibility |
|---|---|---|
| `app.json` | Modify | Add `navigationStyle: "custom"`, remove `pages/chat/chat` |
| `app.js` | No change | Global lifecycle, token restore from storage |
| `config.js` | No change | `apiBase` and `subscribeTemplateId` |
| `pages/login/login.js` | Modify | Add `wxmini_` prefix detection after silent login; pass `js_code` to invite login |
| `pages/login/login.wxml` | Minor modify | Add loading state for auto-login attempt |
| `pages/doctor/doctor.js` | Modify | Add error/retry handling |
| `pages/doctor/doctor.wxml` | Modify | Add `wx:if` error view with retry button |
| `pages/doctor/doctor.wxss` | Modify | Add error view styles |
| `utils/api.js` | Modify | Add `js_code` param to `loginWithInviteCode()` |
| `pages/chat/` | Delete | Unused native chat page (chat is in the WebView now) |

### React Web App (`frontend/web/`)

| File | Action | Responsibility |
|---|---|---|
| `src/utils/env.js` | Create | `isMiniApp()` helper via `window.__wxjs_environment` |
| `src/api/base.js` | Modify | Add 401 callback registration + analytics header |
| `src/App.jsx` | Modify | Register 401 handler with `isMiniApp()` check |
| `index.html` | Modify | Add `viewport-fit=cover` to viewport meta |

---

## Task 1: Update Mini App login flow with `wxmini_` detection

The existing `login.js` has two modes: invite code and WeChat login. After `wx.login()` succeeds, the backend always returns 200 (auto-creates a `wxmini_` stub if needed). We need to detect this and prompt for invite code linking.

**Files:**
- Modify: `frontend/miniprogram/pages/login/login.js`
- Modify: `frontend/miniprogram/utils/api.js`

- [ ] **Step 1: Add `js_code` parameter to `loginWithInviteCode` in `utils/api.js`**

The invite login needs to pass the WeChat `js_code` so the backend can link the `mini_openid`. Change the function signature and data payload:

```js
// utils/api.js — replace loginWithInviteCode
function loginWithInviteCode(code, jsCode) {
  const data = { code };
  if (jsCode) data.js_code = jsCode;
  return request("/api/auth/invite/login", {
    method: "POST",
    data,
  });
}
```

- [ ] **Step 2: Modify `login.js` to detect `wxmini_` prefix and auto-show invite form**

Replace the `onWechatLogin` method. After a successful `wx.login()` → API call, check if `doctor_id` starts with `wxmini_`. If so, save the `js_code` and show the invite code form instead of navigating to the doctor page:

```js
// login.js — add data field
data: {
  mode: "invite",
  inviteCode: "",
  loading: false,
  error: "",
  _wxJsCode: "",  // saved for invite code linking after wxmini_ detection
},

// login.js — replace onWechatLogin
async onWechatLogin() {
  if (this.data.loading) return;
  this.setData({ loading: true, error: "" });
  try {
    const loginRes = await new Promise((resolve, reject) =>
      wx.login({ success: resolve, fail: reject })
    );
    if (!loginRes.code) throw new Error("wx.login 未返回 code");
    const auth = await loginWithWechatCode(loginRes.code, "");

    if (auth.doctor_id && auth.doctor_id.startsWith("wxmini_")) {
      // Auto-created stub — prompt for invite code to link real identity
      this.setData({
        _wxJsCode: loginRes.code,
        mode: "invite",
        error: "",
        loading: false,
      });
      wx.showToast({ title: "请输入邀请码完成注册", icon: "none", duration: 2500 });
      return;
    }

    this._saveAuth(auth);
  } catch (err) {
    const msg = (err && err.message) || "";
    const detail = msg.includes("not configured") ? "后端未配置微信登录" : "微信登录失败，请重试";
    this.setData({ error: detail });
  } finally {
    this.setData({ loading: false });
  }
},
```

- [ ] **Step 3: Modify `onInviteLogin` to pass `js_code` when available**

```js
// login.js — replace onInviteLogin
async onInviteLogin() {
  const code = this.data.inviteCode.trim();
  if (!code) { this.setData({ error: "请输入邀请码" }); return; }
  if (this.data.loading) return;
  this.setData({ loading: true, error: "" });
  try {
    const auth = await loginWithInviteCode(code, this.data._wxJsCode || "");
    this._saveAuth(auth);
  } catch (err) {
    const msg = (err && err.message) || "";
    const detail = msg.includes("401") ? "邀请码无效或已停用" : "登录失败，请重试";
    this.setData({ error: detail });
  } finally {
    this.setData({ loading: false });
  }
},
```

- [ ] **Step 4: Update `onLoad` to attempt silent login automatically**

The current `onLoad` checks for a stored token and validates it. Add: if no stored token, try `wx.login()` silently (same `wxmini_` detection logic). This means returning doctors get instant entry without tapping anything:

```js
// login.js — replace onLoad
async onLoad() {
  const app = getApp();
  const token = app.globalData.accessToken;

  // 1. Try stored token first
  if (token) {
    try {
      const me = await authMe();
      if (me && me.doctor_id) {
        wx.redirectTo({ url: "/pages/doctor/doctor" });
        return;
      }
    } catch {
      this._clearAuth(app);
    }
  }

  // 2. Try silent wx.login() — returning doctors skip the login page entirely
  this.setData({ loading: true });
  try {
    const loginRes = await new Promise((resolve, reject) =>
      wx.login({ success: resolve, fail: reject })
    );
    if (loginRes.code) {
      const auth = await loginWithWechatCode(loginRes.code, "");
      if (auth.doctor_id && !auth.doctor_id.startsWith("wxmini_")) {
        this._saveAuth(auth);
        return;
      }
      // wxmini_ stub — fall through to show login form
    }
  } catch {
    // Silent login failed — show login form
  }
  this.setData({ loading: false });
},
```

- [ ] **Step 5: Add full-page loading overlay to `login.wxml`**

The silent `onLoad` sets `loading: true` while attempting auto-login. The existing WXML only shows loading on button elements. Add a full-page overlay so the doctor doesn't see the login form flash before redirect:

```xml
<!-- Add at the top of login.wxml, before the existing <view class="page"> -->
<view wx:if="{{loading && !error}}" class="loading-overlay">
  <view class="loading-spinner" />
  <text class="loading-hint">正在登录...</text>
</view>

<!-- Wrap existing content to hide during auto-login -->
<view class="page" wx:if="{{!loading || error}}">
  <!-- ... existing card content unchanged ... -->
</view>
```

Add styles to `login.wxss`:

```css
/* Auto-login loading overlay */
.loading-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #f0f7ff 0%, #e8f5f0 100%);
}
.loading-spinner {
  width: 60rpx;
  height: 60rpx;
  border: 6rpx solid #e2e8f0;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 20rpx;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.loading-hint {
  font-size: 28rpx;
  color: #64748b;
}
```

- [ ] **Step 6: Verify in WeChat DevTools**

Open `frontend/miniprogram/` in WeChat DevTools. Test:
1. Mock code `mock:test_openid_linked` → should auto-login (if doctor exists)
2. Mock code `mock:new_openid` → should show invite form
3. Enter invite code → should login and link openid

- [ ] **Step 7: Commit**

```bash
git add frontend/miniprogram/pages/login/ frontend/miniprogram/utils/api.js
git commit -m "feat(miniapp): silent login with wxmini_ detection and invite code linking"
```

---

## Task 2: Update Mini App configuration

**Files:**
- Modify: `frontend/miniprogram/app.json`
- Delete: `frontend/miniprogram/pages/chat/`

- [ ] **Step 1: Update `app.json`**

Add `navigationStyle: "custom"` to hide the native nav bar (the React app has its own header). Remove the unused chat page:

```json
{
  "pages": [
    "pages/login/login",
    "pages/doctor/doctor"
  ],
  "window": {
    "navigationStyle": "custom",
    "navigationBarBackgroundColor": "#ffffff",
    "navigationBarTextStyle": "black"
  },
  "style": "v2",
  "sitemapLocation": "sitemap.json"
}
```

- [ ] **Step 2: Delete unused chat page**

```bash
rm -rf frontend/miniprogram/pages/chat/
```

The chat functionality lives in the React app WebView, not as a native Mini App page.

- [ ] **Step 3: Commit**

```bash
git add frontend/miniprogram/app.json
git rm -r frontend/miniprogram/pages/chat/
git commit -m "refactor(miniapp): custom nav style, remove unused native chat page"
```

---

## Task 3: Add WebView error handling and retry

The existing `doctor.wxml` has no error handling — if the WebView fails to load, the user sees nothing. Add a Chinese-language error view with a retry button.

**Files:**
- Modify: `frontend/miniprogram/pages/doctor/doctor.js`
- Modify: `frontend/miniprogram/pages/doctor/doctor.wxml`
- Modify: `frontend/miniprogram/pages/doctor/doctor.wxss`

- [ ] **Step 1: Add error state and handlers to `doctor.js`**

Add `loadError: false` to data, add `onError` and `onRetry` methods:

```js
// doctor.js — add to data:
loadError: false,

// doctor.js — add methods:
onError(e) {
  console.error("WebView load failed:", e.detail);
  this.setData({ loadError: true, loading: false });
},

onRetry() {
  // Append cache-busting param to force WebView reload (toggling wx:if with same URL
  // does not trigger a re-fetch in some WeChat versions)
  const base = this.data.url.split("?")[0];
  const qs = this.data.url.split("?")[1] || "";
  const bust = "_t=" + Date.now();
  const newUrl = base + "?" + (qs ? qs + "&" : "") + bust;
  this.setData({ url: newUrl, loadError: false, loading: true });
},
```

- [ ] **Step 2: Update `doctor.wxml` with conditional error view**

Replace the WebView line with a conditional that shows an error/retry UI when loading fails:

```xml
<!-- Loading spinner shown while the WebView is fetching the dashboard. -->
<view wx:if="{{loading && url && !loadError}}" class="loading">
  <view class="loading-spinner" />
  <text class="loading-text">加载中…</text>
</view>

<!-- Error view with retry -->
<view wx:if="{{loadError}}" class="error-view">
  <text class="error-icon">⚠️</text>
  <text class="error-text">页面加载失败，请检查网络后重试</text>
  <button class="retry-btn" bindtap="onRetry">重试</button>
</view>

<!-- Main dashboard WebView. -->
<web-view
  wx:if="{{url && !showPermissionPrompt && !loadError}}"
  src="{{url}}"
  bindmessage="onMessage"
  bindload="onWebViewLoad"
  binderror="onError"
/>
```

Note: the existing `<web-view>` line did not have `binderror` — we add it here.

- [ ] **Step 3: Add error view styles to `doctor.wxss`**

```css
/* Error view */
.error-view {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f8fafc;
  padding: 48rpx;
}

.error-icon {
  font-size: 80rpx;
  margin-bottom: 24rpx;
}

.error-text {
  font-size: 30rpx;
  color: #64748b;
  text-align: center;
  margin-bottom: 40rpx;
}

.retry-btn {
  background: #2563eb;
  color: #ffffff;
  font-size: 30rpx;
  font-weight: 600;
  border-radius: 16rpx;
  padding: 24rpx 80rpx;
  border: none;
}

.retry-btn::after {
  border: none;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/miniprogram/pages/doctor/
git commit -m "feat(miniapp): add WebView error handling with retry UI"
```

---

## Task 4: Verify `wx.redirectTo` navigation (no code changes)

The existing code already uses `wx.redirectTo` in both places, which is correct per spec (auth page should not stay on the navigation stack).

**Files:**
- Verify: `frontend/miniprogram/pages/login/login.js` — `_saveAuth()` method
- Verify: `frontend/miniprogram/pages/doctor/doctor.js` — `onLoad()` token guard

- [ ] **Step 1: Verify both use `wx.redirectTo` (not `wx.navigateTo`)**

Check that `_saveAuth` in `login.js` uses `wx.redirectTo({ url: "/pages/doctor/doctor" })` — already correct.
Check that `doctor.js` `onLoad()` uses `wx.redirectTo({ url: "/pages/login/login" })` for missing token — already correct.

No commit needed — verification only.

---

## Task 5: Create `isMiniApp()` helper in React app

**Files:**
- Create: `frontend/web/src/utils/env.js`

- [ ] **Step 1: Create the `utils/` directory and environment detection helper**

Create the directory if it doesn't exist, then create the file:

```bash
mkdir -p frontend/web/src/utils
```

```js
// frontend/web/src/utils/env.js
export const isMiniApp = () => window.__wxjs_environment === "miniprogram";
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/utils/env.js
git commit -m "feat(web): add isMiniApp() environment detection helper"
```

---

## Task 6: Add 401 handler and analytics header to React API layer

**Files:**
- Modify: `frontend/web/src/api/base.js:46-71` (the `request()` function)
- Modify: `frontend/web/src/App.jsx`

- [ ] **Step 1: Add 401 callback registration to `base.js`**

Add after line 77 (the `onAdminAuthError` line), following the same pattern:

```js
let _authExpiredHandler = null;
export function onAuthExpired(handler) { _authExpiredHandler = handler; }
```

- [ ] **Step 2: Add 401 detection to `request()` in `base.js`**

Replace the `if (!response.ok)` block (lines 57-61) with this version that fires the 401 callback before throwing:

```js
if (!response.ok) {
  const err = new Error(await readError(response));
  err.status = response.status;
  if (response.status === 401) { _authExpiredHandler?.(); }
  throw err;
}
```

- [ ] **Step 3: Add `X-Client-Channel` analytics header to `request()` in `base.js`**

In the `request()` function, after line 53 (`if (token && !headers["Authorization"])` block), add:

```js
if (typeof window !== "undefined" && window.__wxjs_environment === "miniprogram") {
  headers["X-Client-Channel"] = "miniapp";
}
```

- [ ] **Step 4: Register the 401 handler in `App.jsx`**

Add imports and a `useEffect` to `App.jsx`:

```js
import { onAuthExpired } from "./api/base";
import { isMiniApp } from "./utils/env";

// Inside App() component, after the existing useEffect:
useEffect(() => {
  onAuthExpired(() => {
    if (isMiniApp()) {
      // Inside Mini App — can't redirect to login, doctor needs to reopen
      alert("会话已过期，请关闭后重新打开小程序");
    } else {
      useDoctorStore.getState().clearAuth();
      window.location.href = "/login";
    }
  });
}, []);
```

Note: Using `alert()` for v1 simplicity. `alert()` may be silently swallowed in some WeChat WebView versions — if testing shows this, switch to a React-rendered overlay or `wx.miniProgram.navigateBack()`. Can upgrade to MUI Snackbar later.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/api/base.js frontend/web/src/App.jsx
git commit -m "feat(web): add 401 expiry handler and miniapp analytics header"
```

---

## Task 7: Add safe area CSS for notched devices

**Files:**
- Modify: `frontend/web/index.html`

- [ ] **Step 1: Add `viewport-fit=cover` to viewport meta in `index.html`**

Change line 5 from:
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
```
to:
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
```

- [ ] **Step 2: Add safe area padding and overscroll-behavior to the root element**

The React app uses MUI's `CssBaseline` which resets body styles. Add inline styles to `index.html`:

```html
<div id="root" style="padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom); overscroll-behavior: none;"></div>
```

Also add `overscroll-behavior: none` to `html` and `body` to prevent pull-to-refresh conflict in the WebView. Add a `<style>` tag in `<head>`:

```html
<style>html, body { overscroll-behavior: none; }</style>
```

All values are harmless in regular browsers (`env()` resolves to 0, `overscroll-behavior: none` just disables the bounce/refresh which is typically unwanted on web apps too).

- [ ] **Step 3: Commit**

```bash
git add frontend/web/index.html
git commit -m "feat(web): add viewport-fit=cover and safe area padding for miniapp"
```

---

## Task 8: Final verification and combined commit

- [ ] **Step 1: Test Mini App auth flow in DevTools**

Open `frontend/miniprogram/` in WeChat DevTools:
1. Clear storage, open app → should attempt silent `wx.login()`, show login form if `wxmini_` stub
2. Enter invite code → should login and navigate to WebView
3. Close and reopen → should auto-login silently (token in storage)

- [ ] **Step 2: Test React app in browser**

Open `http://localhost:5173/doctor` (dev mode). Verify:
1. Normal browser login still works
2. URL with `?token=X&doctor_id=Y&name=Z` still absorbs correctly
3. No visual changes in normal browser mode

- [ ] **Step 3: Test WebView error handling**

In DevTools, set `apiBase` to a bad URL → WebView should show error view with retry button.

- [ ] **Step 4: Push to remotes**

```bash
git push origin main
git push gitee main
```
