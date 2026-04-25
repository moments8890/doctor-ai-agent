# WeChat Miniapp Production Readiness

> **Date:** 2026-03-30
> **Status:** Approved — ready for implementation plan (post-review v2)
> **Scope:** LLM provider switch, miniapp QA, deployment hardening
> **Reviewed by:** Codex (OpenAI) + Claude Agent — findings integrated below

## Context

The doctor-ai-agent WeChat miniapp is published and approved by WeChat review.
ICP 备案 is in regulatory review (管局审核中). The backend runs on Tencent Cloud
CVM via **systemd** (`deploy/tencent/deploy.sh` + `doctor-ai-backend.service`).
Frontend is built locally on the CVM and served as static files. The miniapp is
a thin native shell (login + WebView) that loads the React SPA. The app has not
been tested end-to-end in production.

> **Note:** `.github/workflows/deploy-prod.yml` and `frontend/web/Dockerfile`
> exist but are **unused scaffolding** — they reference missing artifacts
> (`docker-compose.prod.yml`, `nginx.conf`). The actual deploy path is
> `deploy.sh` → `git pull` → `npm build` → `systemctl restart`.

## 1. LLM Provider: Switch to Tencent LKEAP

### Decision

Use **Tencent LKEAP** (hosting DeepSeek V3) as the single LLM provider for both
`ROUTING_LLM` and `STRUCTURING_LLM`. No model split needed at current scale.

### Rationale

| Factor | Tencent LKEAP | DeepSeek Direct | Winner |
|---|---|---|---|
| Latency from Tencent CVM | Same internal network | Public internet hop | LKEAP |
| Reliability | Independent infra | 74+ outages/year | LKEAP |
| Output cost (RMB/M tokens) | 8.00 | 3.05 | DeepSeek |
| Input cost (RMB/M tokens) | 2.00 | 2.03 (cache: 0.20) | Tie / DeepSeek cache |
| Model version | DeepSeek V3 (deepseek-v3-1) | DeepSeek V3.2 | DeepSeek |
| Compliance | Traffic stays in Tencent Cloud | External API egress | LKEAP |

At early stage, reliability and latency outweigh cost. Revisit when monthly LLM
spend exceeds ~500 RMB — at that point, consider DeepSeek direct as primary or
splitting routing to a cheaper model (Qwen3-8B free on SiliconFlow).

### LLM Provider Landscape (China, March 2026)

| Provider / Model | Input (RMB/M) | Output (RMB/M) | Notes |
|---|---|---|---|
| DeepSeek V3.2 (direct) | 2.03 | 3.05 | Cache hits: 0.20 input |
| DeepSeek V3 via Tencent LKEAP | 2.00 | 8.00 | Same-region, selected |
| Qwen3-32B via SiliconFlow | 1.00 | 4.00 | Best cost/quality ratio |
| Qwen3-32B via Alibaba DashScope | 2.00 | 8.00 | Enterprise SLA |
| Qwen3-235B-A22B via DashScope | 2.00 | 8.00 | MoE, strongest overall |
| Qwen3-8B via SiliconFlow | Free | Free | Good for routing tasks |

### Quality Benchmarks

| Benchmark | DeepSeek V3 (671B) | Qwen3-235B (MoE) | Qwen3-32B |
|---|---|---|---|
| MMLU | 87.2 | 87.8 | 83.6 |
| C-Eval (Chinese) | 90.1 | Not reported | Not reported |
| MMLU-Pro | 59.8 | 68.2 | 65.5 |
| GPQA (STEM) | 41.9 | 47.5 | 49.5 |

### Config Changes

```bash
# Production env vars on Tencent CVM
ROUTING_LLM=tencent_lkeap
STRUCTURING_LLM=tencent_lkeap
DIAGNOSIS_LLM=tencent_lkeap          # also used by diagnosis_pipeline.py
TENCENT_LKEAP_API_KEY=<from Tencent Cloud console>
APP_ENV=production                    # required: is_production() gate for mock codes
```

**Code fix required:** `config/runtime.json.vm` line 97 uses `deepseek-v3.1` (dot)
but `src/infra/llm/client.py` line 63 uses `deepseek-v3-1` (dash). Must reconcile
to the correct Tencent LKEAP model name before deploying.

**Fallback caveat:** `LLM_PROVIDER_STRICT_MODE` is defined in config but
**not implemented** — `src/agent/llm.py` hardcodes `fallback_model=None`. If LKEAP
goes down, calls will fail with no automatic fallback. Implementing real fallback
is out of scope for this spec but should be a fast follow.

## 2. Miniapp WebView Audit

### Architecture (current)

```
WeChat App → Miniapp Shell (login.wxml + doctor.wxml)
                ↓ <web-view src="https://api.doctoragentai.cn/doctor?token=...">
             React SPA (Vite + React 19 + MUI 7)
                ↓ fetch()
             FastAPI Backend (Tencent CVM)
                ↓
             Tencent LKEAP (DeepSeek V3)
```

### What's already good

- `viewport-fit=cover` + `env(safe-area-inset-*)` padding
- `overscroll-behavior: none` prevents rubber-banding
- `MobileFrame` wrapper constrains desktop, full-screen on mobile
- `isMiniApp()` detection via `window.__wxjs_environment`
- `X-Client-Channel: miniapp` header sent in API requests
- Auth expiry handling differs between miniapp (alert) and web (redirect)
- Logout sends `postMessage` back to miniapp shell

### Areas to verify in QA

| Area | Risk | What to check |
|---|---|---|
| Token in URL query string | **Medium** | Bearer token visible in WebView history/logs before React hydrates and strips it. Not ideal but acceptable for miniapp with HTTPS. |
| `postMessage` timing | **Medium** | Only fires on navigation/destroy, not realtime. Logout postMessage won't reach shell until next navigation. |
| `localStorage` persistence | Medium | WeChat can clear unexpectedly |
| `position: fixed` in WebView | Low | `transform: translateZ(0)` creates stacking context |
| Bottom nav vs home indicator | Medium | Safe area padding must cover |
| Keyboard behavior in chat | Medium | Input shouldn't be obscured |
| Horizontal scroll | Low | No page should have horizontal overflow |
| Auth expiry in miniapp | **Medium** | 401 triggers `alert()` only — doesn't clear auth or redirect. User stuck after dismissing. |
| Notification prompt repeat | **Medium** | Shows on every load — no session flag to suppress after first prompt. |
| WeChat login enrollment flow | Medium | First-time wx login creates `wxmini_*` placeholder, not a real doctor — must follow with invite code. QA must test both paths. |

## 3. Production QA Checklist

Must be tested on a real device or WeChat DevTools against production URL.

### Critical Path

- [ ] **Invite code login** — enter code → token → WebView loads dashboard
- [ ] **WeChat login** — tap 微信一键登录 → code2session → auth succeeds
- [ ] **WebView loads** — doctor dashboard renders, no blank screen
- [ ] **Chat works** — send message → AI responds (verifies LLM connection)

### Core Features

- [ ] **Auth persistence** — close miniapp → reopen → still logged in
- [ ] **Auth expiry** — expired token → clear message shown
- [ ] **Patient list** — loads, scrolls, tap into detail
- [ ] **Review queue** — load pending, approve/reject
- [ ] **Knowledge base** — view, add URL, add text
- [ ] **Settings** — view and edit doctor profile

### Edge Cases

- [ ] **Notification prompt** — permission card shows → tap → subscribe works
- [ ] **Logout** — tap in WebView → postMessage → miniapp returns to login
- [ ] **Network error** — airplane mode → error view → retry works
- [ ] **Keyboard** — chat input visible above keyboard
- [ ] **Safe areas** — no content behind notch/home indicator
- [ ] **Horizontal scroll** — none on any page

## 4. Deployment Hardening

### Required env vars (verify on Tencent CVM)

| Var | Purpose | Action |
|---|---|---|
| `TENCENT_LKEAP_API_KEY` | LLM provider auth | Add |
| `ROUTING_LLM=tencent_lkeap` | LLM routing | Change |
| `STRUCTURING_LLM=tencent_lkeap` | LLM structuring | Change |
| `DIAGNOSIS_LLM=tencent_lkeap` | Diagnosis pipeline | **Add** (missed in v1) |
| `APP_ENV=production` | Production gate (disables mock codes) | **Add** (critical) |
| `WECHAT_MINI_APP_ID` | WeChat login | Verify exists |
| `WECHAT_MINI_APP_SECRET` | WeChat login | Verify exists |

### Deployment model (actual)

Production uses `deploy/tencent/deploy.sh`:
1. `git fetch origin && git reset --hard origin/main`
2. `pip install -r requirements.txt`
3. `cd frontend/web && npm ci && npm run build` → copies to `frontend/dist/`
4. `systemctl restart doctor-ai-backend`

The backend is managed by systemd (`doctor-ai-backend.service`), not Docker.
The `.github/workflows/deploy-prod.yml` Docker workflow is unused scaffolding.

### Pre-flight checks

- [ ] **Model name reconciliation** — `config/runtime.json.vm` says `deepseek-v3.1`
  (dot), `src/infra/llm/client.py` says `deepseek-v3-1` (dash). Verify correct
  model name against Tencent LKEAP API docs and fix the mismatch.
- [ ] **WebView domain whitelist** — `api.doctoragentai.cn` registered in
  WeChat admin (开发管理 → 开发设置 → 业务域名)
- [ ] **HTTPS certificate** — valid and not expiring soon
- [ ] **ICP 备案 contingency** — note: IP-direct access only helps for non-miniapp
  testing. The miniapp WebView validates against the registered business domain list,
  so IP access won't work there.
- [ ] **LKEAP connectivity test** — after setting API key, verify with a curl call
  to LKEAP endpoint before relying on deploy health check (which only checks FastAPI
  process, not LLM connectivity)

## 5. Known Issues (from review, fix during implementation)

- **Auth expiry in miniapp** — 401 triggers `alert()` but doesn't clear auth or
  redirect. User gets stuck. Need to add `clearAuth()` + redirect after alert.
- **Notification prompt spam** — shows on every page load, no session flag.
  Add `wx.getStorageSync("permission_prompted")` guard.
- **postMessage logout delay** — logout postMessage won't reach miniapp shell
  until WebView navigates. Consider using `wx.miniProgram.navigateBack()` from
  WebView JS to force the transition.
- **Raw openid in login response** — `MiniProgramLoginResponse.wechat_openid`
  returns unhashed openid over the wire. Remove from response or hash it.
- **No real LLM fallback** — `fallback_model=None` hardcoded. If LKEAP goes
  down, all LLM calls fail. Implement actual fallback as fast-follow.

## 6. Future Optimizations (not in scope now)

- **Split LLM routing**: use Qwen3-8B (free) for intent classification, keep
  DeepSeek V3 for medical structuring — when monthly spend exceeds 500 RMB
- **DeepSeek direct as fallback**: add as secondary provider once LKEAP is
  proven stable — requires implementing real fallback in `llm.py`
- **Taro/uni-app migration**: replace WebView with native miniapp framework —
  only if WebView limitations become blocking (unlikely for this use case)
- **LLM cost monitoring**: aggregate token counts from `logs/llm_calls.jsonl`
  and alert when approaching budget threshold

## Appendix: Review Findings

### Cross-model review (2026-03-30)

Reviewed by Codex (OpenAI) and Claude Agent independently.

**Both found:** Dockerfile broken, fallback is fake, model name mismatch,
token-in-URL risk, DIAGNOSIS_LLM missing, notification prompt spam, deploy
artifacts missing.

**Only Codex found:** deploy.sh vs Docker Compose contradiction, miniapp
release pipeline disconnection, missing rollback plan.

**Only Claude found:** raw openid leak, APP_ENV not set, no LKEAP health check,
session_key management gap.

**Agreement rate:** ~70% (10/14 unique findings overlap)
