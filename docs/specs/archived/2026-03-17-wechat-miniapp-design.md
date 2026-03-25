# WeChat Mini App — Thin WebView Shell Design ✅ DONE

> **Status: ✅ DONE** — spec implemented and shipped.

**Date:** 2026-03-17
**Status:** Draft
**Goal:** Wrap the existing React web app inside a WeChat Mini App using the `<web-view>` component, enabling distribution and access through WeChat with minimal code changes.

---

## 1. Context

The Doctor AI Agent has a React web frontend (`frontend/`) and a WeChat/WeCom text channel (`channels/wechat/`). WeChat is the dominant platform in China — doctors already interact via the text channel. Placing the full web app inside a Mini App gives us:

- **Distribution** — doctors find/share the app within WeChat
- **Unified experience** — chat channel + workspace in one app
- **Future native APIs** — subscription messages, share cards, QR scanning, etc.

The backend already supports Mini App auth (`/api/auth/wechat-mini/login` with `code2session`), and the Mini App is registered but not yet configured.

## 2. Approach

**Thin Native Shell** — the Mini App has two native pages:

1. `pages/auth/auth` — handles `wx.login()` and invite code fallback
2. `pages/main/main` — a single `<web-view>` loading the existing React app

The React app runs nearly unchanged inside the WebView (small boot-sequence delta). The backend requires zero modifications.

### Why not other approaches

| Alternative | Why rejected |
|---|---|
| Native shell + PostMessage bridge | Over-engineering for v1; bridge adds complexity before any native feature is needed |
| Progressive native rewrite | 3-5x longer to ship, dual codebase maintenance |

The architecture anticipates the PostMessage bridge — it can be added incrementally when the first native feature (subscription messages, share cards, etc.) is needed.

## 3. Architecture

```
┌─────────────────────────┐     ┌──────────────────────────┐     ┌─────────────────┐
│  WeChat Mini App Shell  │     │  React App (in WebView)  │     │  Backend (FastAPI)│
│                         │     │                          │     │                  │
│  pages/auth/auth        │     │  Boot: extract ?token=   │     │  /api/auth/      │
│  • wx.login() → code    │────▶│  • Store in Zustand      │────▶│  /api/records/   │
│  • POST /auth/wechat-   │     │  • Strip URL params      │     │  /api/tasks/     │
│    mini/login            │     │  • Skip login page       │     │  /api/patients/  │
│  • Fallback: invite form│     │  • Everything else same   │     │  /api/export/    │
│                         │     │                          │     │                  │
│  pages/main/main        │     │  Mini adaptations:       │     │  Zero changes    │
│  • <web-view src=URL>   │     │  • __wxjs_environment    │     │                  │
│                         │     │  • Disable pull-refresh   │     │                  │
│                         │     │  • 401 → "reopen" msg    │     │                  │
└─────────────────────────┘     └──────────────────────────┘     └─────────────────┘
```

## 4. Authentication Flow

### 4.1 Returning doctor (happy path)

1. Mini App opens → `pages/auth/auth` loads
2. `wx.login()` → WeChat returns `js_code`
3. `POST /api/auth/wechat-mini/login { code: js_code }` → backend calls `code2session`, looks up `mini_openid`
4. Backend always returns 200 with JWT + `doctor_id`. If `mini_openid` is linked to an existing doctor, that doctor's ID is returned. Otherwise, a new `wxmini_` doctor is auto-created.
5. Shell checks `doctor_id`: if it does **not** start with `wxmini_`, the doctor is recognized → proceed to WebView.
6. `wx.redirectTo('/pages/main/main?token=' + jwt + '&doctor_id=' + doctorId + '&name=' + name + '&mini=1')`
7. WebView loads `https://domain.com/app?token={jwt}&doctor_id={id}&name={name}&mini=1`
8. React app's existing `App.jsx` boot code extracts `token`, `doctor_id`, `name` → stores in Zustand → strips params via `history.replaceState()` → navigates to DoctorPage

> **Note:** `wx.redirectTo` is used (not `wx.navigateTo`) so the auth page is removed from the navigation stack. The doctor cannot press back into the auth screen.

### 4.2 New doctor (fallback)

The `/api/auth/wechat-mini/login` endpoint never returns 404 — it always upserts. The fallback is triggered client-side:

1. Steps 1-4 same as happy path
2. Shell checks `doctor_id`: if it starts with `wxmini_`, this is an auto-created stub (no invite code linked)
3. Auth page shows native invite code form (WXML) — the `wxmini_` stub exists in the DB but the doctor hasn't claimed a real identity yet
4. Doctor enters invite code + specialty
5. `POST /api/auth/invite/login { code, specialty, js_code }` — backend resolves the invite code's doctor, links `mini_openid` via `js_code`
6. New JWT returned with the real `doctor_id` → continue from step 6 above

> **Note:** The `wxmini_` stub doctor created in step 4 becomes orphaned after invite linking. This is acceptable — no patient data was attached to it. The `doctors` table already has `created_at` — future cleanup: `DELETE FROM doctors WHERE doctor_id LIKE 'wxmini_%' AND created_at < NOW() - INTERVAL 30 DAY AND doctor_id NOT IN (SELECT DISTINCT doctor_id FROM patients)`.

### 4.3 Token expiry

- JWT TTL: 7 days (current setting)
- React app receives 401 → if `isMiniApp()`, shows "Session expired, please reopen the Mini App"
- Doctor closes and reopens Mini App → shell re-authenticates silently via `wx.login()`
- No complex token refresh mechanism needed for v1

## 5. Mini App Project Structure

All Mini App files live under `frontend/miniapp/`, alongside the existing React web app in `frontend/web/src/`:

```
frontend/
├── src/                  ← mobile (Capacitor) build — not used by Mini App
├── web/
│   └── src/              ← React web app (served to <web-view>)
├── public/
├── package.json
├── vite.config.js
└── miniapp/              ← new Mini App shell
    ├── app.js            — global lifecycle
    ├── app.json          — page routes, window config
    ├── app.wxss          — global styles (minimal)
    ├── project.config.json — DevTools project settings
    ├── sitemap.json      — search indexing rules
    ├── pages/
    │   ├── auth/
    │   │   ├── auth.wxml — loading spinner + invite code form
    │   │   ├── auth.js   — wx.login() → API → navigate
    │   │   ├── auth.wxss — auth page styles
    │   │   └── auth.json — page config
    │   └── main/
    │       ├── main.wxml — single <web-view> tag
    │       ├── main.js   — receive token, build URL
    │       ├── main.wxss — (empty)
    │       └── main.json — page config
    └── utils/
        ├── api.js        — wx.request() wrapper
        └── config.js     — API_BASE_URL, WEBVIEW_BASE_URL
```

**~10 files, ~150 lines of code total.**

### 5.1 Key configurations

**app.json:**
```json
{
  "pages": [
    "pages/auth/auth",
    "pages/main/main"
  ],
  "window": {
    "navigationStyle": "custom",
    "navigationBarTextStyle": "black"
  }
}
```

`navigationStyle: "custom"` hides the default Mini App title bar since the React app has its own header.

**pages/main/main.wxml:**
```xml
<!-- bindmessage is a no-op placeholder for v1; will be used when PostMessage bridge is added -->
<web-view
  wx:if="{{!loadError}}"
  src="{{webviewUrl}}"
  bindmessage="onMessage"
  binderror="onError"
/>
<view wx:else style="text-align:center; padding-top:40%;">
  <text>页面加载失败，请检查网络后重试</text>
  <button bindtap="onRetry" style="margin-top:24px;">重试</button>
</view>
```

**pages/main/main.js** (error handling):
```js
onError(e) {
  console.error('WebView load failed:', e.detail);
  this.setData({ loadError: true });
},
onRetry() {
  this.setData({ loadError: false });
}
```

## 6. React App Adaptations

The existing `frontend/web/src/App.jsx` (lines 33-44) already absorbs `token`, `doctor_id`, and `name` from URL params, stores them in Zustand, and strips them via `history.replaceState()`. This was built for the Mini App handoff and works as-is. The only new work is adding Mini App environment detection and 401 handling.

**Changes needed (~15 lines across 3 files):**

### 6.1 Mini App detection (runtime, no store changes)

WeChat's JS bridge sets `window.__wxjs_environment === 'miniprogram'` inside any `<web-view>`. Use this as the runtime check instead of persisting a flag in the Zustand store — zero state, always correct, can't go stale:

```js
// frontend/web/src/utils/env.js (new file, 1 line)
export const isMiniApp = () => window.__wxjs_environment === 'miniprogram';
```

No changes needed to `frontend/web/src/store/doctorStore.js`. No need to read or strip a `mini` URL param.

`isMiniApp()` is used to:
- Hide any browser-specific UI (e.g., "open in browser" links)
- Disable pull-to-refresh CSS (`overscroll-behavior: none`) to avoid conflict with WebView scrolling
- Adjust 401 handling (see below)
- Set `X-Client-Channel: miniapp` header for analytics (see 6.4)

### 6.2 Token expiry handling (`frontend/web/src/api/base.js`, ~8 lines)

Add a 401 callback following the existing pattern used by `adminRequest` (which handles 403/503 via `_adminAuthErrorHandler`):

```js
// base.js — new callback registration
let _authExpiredHandler = null;
export function onAuthExpired(handler) { _authExpiredHandler = handler; }

// Inside request(), after the error throw on non-ok response:
if (response.status === 401) { _authExpiredHandler?.(); }
```

Register the handler once in `frontend/web/src/App.jsx`:

```js
import { onAuthExpired } from "./api/base";
import { isMiniApp } from "./utils/env";

useEffect(() => {
  onAuthExpired(() => {
    if (isMiniApp()) {
      // toast: "会话已过期，请重新打开小程序"
    } else {
      clearAuth();
      window.location.href = "/login";
    }
  });
}, []);
```

### 6.3 Safe area CSS (`frontend/web/src/index.css` or root layout)

Since the Mini App uses `navigationStyle: "custom"`, content may extend under the phone's status bar (top) and home indicator (bottom) on notched devices.

**Prerequisite:** Add `viewport-fit=cover` to `frontend/web/index.html` — without this, the `env()` vars resolve to 0:

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
```

Then add to the root element:

```css
padding-top: env(safe-area-inset-top);
padding-bottom: env(safe-area-inset-bottom);
```

Both are harmless in regular browsers (`viewport-fit=cover` is a no-op without a notch, and the env vars resolve to 0).

### 6.4 Analytics header (`frontend/web/src/api/base.js`, ~3 lines)

Add a channel header so the backend can distinguish Mini App traffic without any backend code change:

```js
// In request(), when building headers:
if (window.__wxjs_environment === 'miniprogram') {
  headers["X-Client-Channel"] = "miniapp";
}
```

The backend can log this via nginx `$http_x_client_channel` or middleware when analytics is needed.

## 7. WeChat Admin Console Configuration

Before the Mini App can load the web app, configure in [WeChat Mini App admin console](https://mp.weixin.qq.com):

| Setting | Value | Purpose |
|---|---|---|
| Business Domain (业务域名) | `your-domain.com` | Required for `<web-view>` to load your URL |
| Server Domain — request (服务器域名) | `your-domain.com` | Auth page calls backend via `wx.request()` |
| AppID / AppSecret | Already in `config/runtime.json` | No change |
| CSP / X-Frame-Options | Do not set `frame-ancestors` or `X-Frame-Options: DENY` | Would block `<web-view>` from loading the page |

**Requirements:**
- Upload verification file to web server root for business domain
- HTTPS required for both WebView URL and API endpoint (WeChat enforces strictly)

## 8. Security

### 8.1 JWT in URL query parameter

The `<web-view>` component does not support custom request headers, so the JWT is passed via `?token=...`. Mitigations:

- **Immediate extraction** — React app reads token on boot, stores in Zustand, then calls `history.replaceState()` to strip it from URL. Token never persists in browser history or referrer headers.
- **HTTPS enforced** — WeChat requires HTTPS for `<web-view>` domains. Token encrypted in transit.
- **Server-side log hygiene** — Confirm web server (nginx/etc.) and any CDN/WAF (Cloudflare, Tencent Cloud CDN) do not log query parameters, or add a rule to mask the `token` param.

### 8.2 No privilege escalation

- The JWT from `/api/auth/wechat-mini/login` has the same 7-day TTL and permissions as the web login JWT
- `mini=1` flag is cosmetic (passed in URL for legacy compat); runtime detection uses `window.__wxjs_environment`, not an auth bypass
- All API calls validate the JWT as before

## 9. Backend Changes

**None.** The existing endpoints are sufficient:

- `POST /api/auth/wechat-mini/login` — silent login with `code2session` ✅
- `POST /api/auth/invite/login` — invite code with optional `js_code` for `mini_openid` linking ✅
- All CRUD APIs — channel-agnostic, JWT-authenticated ✅

## 10. Future Roadmap (Native Features)

Not built in v1. When needed, add a PostMessage bridge (`utils/bridge.js` in Mini App, `miniAppBridge.js` in React app):

| Feature | Trigger | Implementation |
|---|---|---|
| Subscription messages | Task reminder push | Shell: `wx.requestSubscribeMessage()`, backend: template message API |
| WeChat Pay | Consultation billing | Shell: `wx.requestPayment()`, React sends order via postMessage |
| Share cards | Doctor shares patient cards | Shell: `wx.showShareMenu()`, React provides share data |
| Phone quick-fill | Patient registration | Shell: `wx.getPhoneNumber()`, encrypted data to backend |
| QR scanning | Link patient by code | Shell: `wx.scanCode()`, result to WebView |
| Voice input | WeChat voice recognition | Shell: `wx.startRecord()`, audio to backend |

**Upgrade path:** Each feature is a message type added to the bridge incrementally. The React app calls `window.wx.miniProgram.postMessage()` to request a native capability; the shell fulfills it and responds via `bindmessage`.

## 11. Testing Strategy

- **DevTools** — Open `frontend/miniapp/` in WeChat DevTools, test auth flow with mock codes (`WECHAT_MINI_ALLOW_MOCK_CODE=true`)
- **Real device** — Preview via DevTools QR code, test on actual WeChat
- **WebView debugging** — Enable vConsole in DevTools for WebView JS debugging
- **Existing tests** — All backend tests remain valid (no backend changes). Frontend tests unchanged.

## 12. Deployment Sequence

1. Configure business domain + server domain in WeChat admin console
2. Ensure `VITE_API_BASE_URL` is set correctly for the **web build** (`frontend/web/`) production build (currently same-origin; if WebView URL and API split to different domains, set `VITE_API_BASE_URL` at build time)
3. Ensure the web server serves `index.html` with `Cache-Control: no-cache, must-revalidate` — prevents the Mini App WebView from loading a stale entry point after a React app deployment (hashed JS/CSS assets from Vite can use long-lived caching)
4. Deploy React app with Mini App adaptations (works for both web and Mini App)
5. Upload Mini App code via WeChat DevTools
6. Submit for WeChat review (typically 1-3 business days)
7. Publish after approval

## 13. Open Questions

- **Domain verification timing** — Business domain verification requires uploading a file to the server root. Coordinate with deployment.
- **WeChat review requirements** — First submission may require additional materials (privacy policy page, category qualification). Check category requirements for medical/health apps.
- **Offline behavior** — v1 has no offline support. If the network is unavailable, the WebView shows a blank page. Consider adding an error page in a future iteration.
