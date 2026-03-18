# ADR 0017: WeChat Mini App — Thin WebView Shell

## Status

Proposed

## Date

2026-03-17

## Implementation Status

Not Started

Last reviewed: 2026-03-17

Notes:

- Spec: `docs/superpowers/specs/2026-03-17-wechat-miniapp-design.md`

## Context

WeChat is the dominant platform in China. Doctors already use the WeChat/WeCom
text channel (`channels/wechat/`). Placing the full web app inside a Mini App
enables discovery, sharing, and a unified experience — chat + workspace in one
app.

Current state:

1. **React web app exists** — `frontend/web/src/`, Vite build, Zustand auth
   store, production-deployed.

2. **Backend auth is ready** — `POST /api/auth/wechat-mini/login` (silent
   login via `code2session`, auto-creates `wxmini_` stub doctors) and
   `POST /api/auth/invite/login` (invite code with `js_code` for
   `mini_openid` linking) are both implemented and tested.

3. **Mini App is registered** — AppID/AppSecret in `config/runtime.json`,
   but no code uploaded yet.

## Decision

Use a **thin native shell** with two pages wrapping the existing React app in a
`<web-view>` component:

1. `pages/auth/auth` — `wx.login()` → backend → JWT. Returning doctors proceed
   directly; new doctors see an invite code form.
2. `pages/main/main` — a single `<web-view>` loading the React web app with
   JWT passed via URL query parameter.

Key design choices:

- **Runtime Mini App detection** via `window.__wxjs_environment === 'miniprogram'`
  (set by WeChat's JS bridge) instead of persisting an `isMiniApp` flag in the
  Zustand store. Zero state, always correct.

- **401 callback pattern** — `onAuthExpired()` in `api/base.js`, matching the
  existing `onAdminAuthError()` pattern. Mini App shows "reopen" message;
  browser redirects to `/login`.

- **PostMessage bridge deferred** — the `<web-view>` `bindmessage` handler is
  a no-op in v1. Native features (subscription messages, WeChat Pay, share
  cards, etc.) are added incrementally via bridge messages when needed.

- **No backend changes** — all existing endpoints are channel-agnostic and
  JWT-authenticated. The React app adds an `X-Client-Channel: miniapp` header
  for analytics without requiring backend code changes.

### Alternatives rejected

| Alternative | Why rejected |
|---|---|
| Native shell + PostMessage bridge from day 1 | Over-engineering; bridge adds complexity before any native feature is needed |
| Progressive native rewrite (WXML/WXS) | 3-5x longer to ship, dual codebase maintenance |

## Consequences

### Positive

- **~10 Mini App files, ~150 LOC** — minimal surface area to build, review,
  and maintain.
- **~15 lines of React changes** across 3 files (`utils/env.js`, `api/base.js`,
  `App.jsx`) plus 1 CSS line and 1 viewport meta tag.
- **Zero backend changes** — all APIs reused as-is.
- **Incremental upgrade path** — PostMessage bridge can be added per-feature
  without rewriting the shell.

### Negative

- **No offline support** — WebView shows blank on network failure (mitigated
  by error page with retry button in the shell).
- **Native features require bridge work** — subscription messages, WeChat Pay,
  share cards each need a bridge message type added later.
- **JWT in URL query parameter** — mitigated by immediate `replaceState()`
  stripping, HTTPS enforcement, and server-side log hygiene.
- **Orphaned `wxmini_` doctor stubs** — curious users who open the Mini App
  but never enter an invite code leave stub rows. Cleanup query documented in
  spec; `doctors.created_at` column already exists.

### Deployment prerequisites

- Business domain + server domain configured in WeChat admin console
- No `Content-Security-Policy: frame-ancestors` or `X-Frame-Options: DENY`
  headers on the web server
- `index.html` served with `Cache-Control: no-cache, must-revalidate`
- `viewport-fit=cover` added to viewport meta tag for safe-area support
