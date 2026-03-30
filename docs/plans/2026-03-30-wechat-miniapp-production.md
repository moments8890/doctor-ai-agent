# WeChat Miniapp Production Readiness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch LLM to Tencent LKEAP, fix known miniapp bugs, verify production deployment end-to-end.

**Architecture:** Thin WeChat miniapp shell (2 pages: login + WebView) loads a React SPA from `api.doctoragentai.cn`. Backend is FastAPI on Tencent CVM via systemd. LLM calls go through OpenAI-compatible client to Tencent LKEAP.

**Tech Stack:** Python/FastAPI, React 19/MUI 7/Vite, WeChat miniprogram native, Tencent LKEAP (DeepSeek V3)

**Spec:** `docs/specs/2026-03-30-wechat-miniapp-production-design.md`

**SSH alias:** `ssh tencent` connects to production CVM.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `config/runtime.json.vm` | Modify | Fix model name typo |
| `config/runtime.json` | Modify | Switch LLM provider to tencent_lkeap |
| `src/channels/web/auth/miniapp.py` | Modify | Remove raw openid from response |
| `frontend/miniprogram/pages/doctor/doctor.js` | Modify | Fix notification prompt spam |
| `frontend/web/src/App.jsx` | Modify | Fix auth expiry in miniapp mode |

---

### Task 1: Fix model name mismatch in runtime.json.vm

**Files:**
- Modify: `config/runtime.json.vm:96-97`

The template says `deepseek-v3.1` (dot) but `client.py` and `runtime_config.py`
both default to `deepseek-v3-1` (dash). The correct name for Tencent LKEAP API
is `deepseek-v3` (verify first).

- [ ] **Step 1: Verify the correct model name on Tencent LKEAP**

```bash
ssh tencent 'curl -s https://api.lkeap.cloud.tencent.com/v1/models \
  -H "Authorization: Bearer $(grep TENCENT_LKEAP_API_KEY /home/ubuntu/doctor-ai-agent/config/runtime.json 2>/dev/null | head -1 | sed "s/.*: *\"//;s/\".*//")" | python3 -m json.tool | head -40'
```

If no API key is set yet, check the Tencent Cloud LKEAP docs for the correct model
name. Common names: `deepseek-v3`, `deepseek-v3-0324`, `deepseek-chat`.

- [ ] **Step 2: Fix the model name in runtime.json.vm**

In `config/runtime.json.vm` line 97, change the value to match whatever the
LKEAP `/v1/models` endpoint returns. For example if it returns `deepseek-v3`:

```json
"TENCENT_LKEAP_MODEL": {
  "value": "deepseek-v3",
```

Also update the default in `src/infra/llm/client.py` line 63 to match:

```python
"model": os.environ.get("TENCENT_LKEAP_MODEL", "deepseek-v3"),
```

And `src/utils/runtime_config.py` line 31:

```python
"TENCENT_LKEAP_MODEL": "deepseek-v3",
```

All three must agree.

- [ ] **Step 3: Commit**

```bash
git add config/runtime.json.vm src/infra/llm/client.py src/utils/runtime_config.py
git commit -m "fix: reconcile LKEAP model name across config files"
```

---

### Task 2: Switch runtime config to Tencent LKEAP

**Files:**
- Modify: `config/runtime.json`

- [ ] **Step 1: Update local runtime.json**

In `config/runtime.json`, change these values:

```json
"ROUTING_LLM": {
  "value": "tencent_lkeap",
```

```json
"STRUCTURING_LLM": {
  "value": "tencent_lkeap",
```

Find `DIAGNOSIS_LLM` and set it:

```json
"DIAGNOSIS_LLM": {
  "value": "tencent_lkeap",
```

- [ ] **Step 2: Commit**

```bash
git add config/runtime.json
git commit -m "feat: switch LLM provider to Tencent LKEAP"
```

---

### Task 3: Fix auth expiry handling in miniapp mode

**Files:**
- Modify: `frontend/web/src/App.jsx:174-184`

Currently, a 401 in miniapp mode shows `alert()` but doesn't clear auth or
redirect. The user gets stuck after dismissing the alert.

- [ ] **Step 1: Fix the auth expiry handler**

In `frontend/web/src/App.jsx`, find lines 174-184 and replace the `isMiniApp()` branch:

```jsx
  useEffect(() => {
    onAuthExpired(() => {
      if (isMiniApp()) {
        // Clear auth state so WebView doesn't keep using the expired token
        useDoctorStore.getState().clearAuth();
        alert("会话已过期，请关闭后重新打开小程序");
        // Tell miniapp shell to navigate back to login
        wx.miniProgram?.navigateBack?.();
      } else {
        useDoctorStore.getState().clearAuth();
        window.location.href = "/login";
      }
    });
  }, []);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/App.jsx
git commit -m "fix: clear auth and notify miniapp shell on token expiry"
```

---

### Task 4: Fix notification prompt showing on every page load

**Files:**
- Modify: `frontend/miniprogram/pages/doctor/doctor.js:34-39`

Currently `showPermissionPrompt` is set to `true` on every `onLoad` if
`subscribeTemplateId` exists. There's no guard to skip after the first prompt.

- [ ] **Step 1: Add session storage guard**

In `frontend/miniprogram/pages/doctor/doctor.js`, replace lines 34-39:

```js
    // Show the permission prompt only once per install (not every load).
    if (runtimeConfig.subscribeTemplateId && !wx.getStorageSync("permission_prompted")) {
      this.setData({ showPermissionPrompt: true, loading: false });
    }
```

Then in the `onEnterTap` method, after the `wx.requestSubscribeMessage` call,
mark the flag. Replace the `complete` callback (around line 49-51):

```js
        complete: () => {
          wx.setStorageSync("permission_prompted", "1");
          this.setData({ showPermissionPrompt: false, loading: true });
        },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/miniprogram/pages/doctor/doctor.js
git commit -m "fix: only show notification permission prompt once per install"
```

---

### Task 5: Remove raw openid from login response

**Files:**
- Modify: `src/channels/web/auth/miniapp.py:38-44`

The `MiniProgramLoginResponse` returns unhashed `wechat_openid` over the wire.
The miniapp login.js doesn't use this field. Remove it.

- [ ] **Step 1: Remove wechat_openid from the response model**

In `src/channels/web/auth/miniapp.py`, change the response model (lines 38-44):

```python
class MiniProgramLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    doctor_id: str
    channel: str
```

Then update the endpoint return (around line 253-261) to remove `wechat_openid`:

```python
    return MiniProgramLoginResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=604800,
        doctor_id=doctor_id,
        channel="wechat_mini",
    )
```

- [ ] **Step 2: Run tests**

```bash
/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/ -k "auth or miniapp or login" -v --rootdir=/Volumes/ORICO/Code/doctor-ai-agent
```

Expected: no failures (the field is not referenced in tests).

- [ ] **Step 3: Commit**

```bash
git add src/channels/web/auth/miniapp.py
git commit -m "fix: remove raw openid from miniapp login response"
```

---

### Task 6: Deploy to production and set env vars

This task requires SSH access to the production CVM via `ssh tencent`.

- [ ] **Step 1: Push code changes to main**

```bash
git push origin main
```

- [ ] **Step 2: SSH to production and pull latest code**

```bash
ssh tencent 'cd /home/ubuntu/doctor-ai-agent && git fetch origin && git reset --hard origin/main'
```

- [ ] **Step 3: Check current env vars on production**

```bash
ssh tencent 'cat /home/ubuntu/doctor-ai-agent/config/runtime.json | python3 -c "
import sys, json
cfg = json.load(sys.stdin)
cats = cfg.get(\"categories\", {})
for cat in cats.values():
    for k, v in cat.get(\"settings\", {}).items():
        if k in (\"ROUTING_LLM\", \"STRUCTURING_LLM\", \"DIAGNOSIS_LLM\", \"TENCENT_LKEAP_API_KEY\", \"TENCENT_LKEAP_MODEL\", \"WECHAT_MINI_APP_ID\", \"WECHAT_MINI_APP_SECRET\"):
            val = v.get(\"value\", \"\") if isinstance(v, dict) else v
            masked = val[:4] + \"***\" if len(str(val)) > 8 else val
            print(f\"{k} = {masked}\")
"'
```

Review the output. The following must be set:
- `ROUTING_LLM` = `tencent_lkeap`
- `STRUCTURING_LLM` = `tencent_lkeap`
- `DIAGNOSIS_LLM` = `tencent_lkeap`
- `TENCENT_LKEAP_API_KEY` = a real key (not empty or placeholder)
- `WECHAT_MINI_APP_ID` = your miniapp ID
- `WECHAT_MINI_APP_SECRET` = your miniapp secret

If `TENCENT_LKEAP_API_KEY` is not set, you need to get it from
[Tencent Cloud LKEAP console](https://console.cloud.tencent.com/lke).

- [ ] **Step 4: Check ENVIRONMENT is set for production**

```bash
ssh tencent 'grep -i "ENVIRONMENT\|APP_ENV" /home/ubuntu/doctor-ai-agent/.env 2>/dev/null; systemctl cat doctor-ai-backend 2>/dev/null | grep -i "ENVIRONMENT\|APP_ENV"'
```

If neither `ENVIRONMENT=production` nor `APP_ENV=production` is set anywhere,
add it to the systemd service or `.env` file. This is critical — without it,
`is_production()` returns `False` and mock auth codes could work in production.

- [ ] **Step 5: Rebuild frontend and restart backend**

```bash
ssh tencent 'cd /home/ubuntu/doctor-ai-agent && \
  .venv/bin/pip install -q -r requirements.txt && \
  cd frontend/web && npm ci --silent && npm run build && \
  rm -rf /home/ubuntu/doctor-ai-agent/frontend/dist && \
  cp -r /home/ubuntu/doctor-ai-agent/frontend/web/dist /home/ubuntu/doctor-ai-agent/frontend/dist && \
  chmod -R o+rX /home/ubuntu/doctor-ai-agent/frontend/dist && \
  cd /home/ubuntu/doctor-ai-agent && \
  sudo systemctl restart doctor-ai-backend'
```

- [ ] **Step 6: Verify backend is running**

```bash
ssh tencent 'curl -fsS http://127.0.0.1:8000/healthz && echo " OK"'
```

Expected: `{"status":"ok"}` or similar health response + " OK"

---

### Task 7: Verify LKEAP connectivity from production

- [ ] **Step 1: Test LKEAP API directly from CVM**

```bash
ssh tencent 'cd /home/ubuntu/doctor-ai-agent && .venv/bin/python3 -c "
import asyncio, os, json
# Load runtime config to get API key
with open(\"config/runtime.json\") as f:
    cfg = json.load(f)
cats = cfg.get(\"categories\", {})
for cat in cats.values():
    for k, v in cat.get(\"settings\", {}).items():
        val = v.get(\"value\", \"\") if isinstance(v, dict) else v
        if val and val != \"<TENCENT_LKEAP_API_KEY>\":
            os.environ.setdefault(k, str(val))
# Override for this test
os.environ[\"ROUTING_LLM\"] = \"tencent_lkeap\"
from src.agent.llm import llm_call
async def test():
    result = await llm_call(\"lkeap_test\", [{\"role\": \"user\", \"content\": \"你好，请用一句话介绍你自己\"}])
    print(f\"LKEAP response: {result[:100]}\")
    print(\"SUCCESS\")
asyncio.run(test())
"'
```

Expected: A Chinese response from DeepSeek V3 + "SUCCESS" at the end.

If this fails, check the API key and model name. Common issues:
- Wrong model name (check Task 1)
- API key not set or invalid
- Network connectivity (LKEAP should be reachable from Tencent internal network)

- [ ] **Step 2: Test via the actual API endpoint**

```bash
ssh tencent 'curl -s http://127.0.0.1:8000/api/auth/invite/login \
  -H "Content-Type: application/json" \
  -d "{\"invite_code\": \"YOUR_TEST_INVITE_CODE\"}" | python3 -m json.tool'
```

Replace `YOUR_TEST_INVITE_CODE` with a valid invite code. This verifies the full
auth → token flow works.

Then test a chat message:

```bash
ssh tencent 'TOKEN="<token_from_above>"; curl -s http://127.0.0.1:8000/api/doctor/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"你好\"}" | python3 -m json.tool | head -20'
```

Expected: An AI-generated response (verifies full LLM pipeline works).

---

### Task 8: Verify miniapp WebView domain whitelist

- [ ] **Step 1: Check WeChat admin console**

Open WeChat Mini Program admin console:
1. Go to 开发管理 → 开发设置 → 业务域名
2. Verify `api.doctoragentai.cn` is listed
3. Also check: 服务器域名 → request合法域名 includes `api.doctoragentai.cn`

If not listed, add it. Note: adding a business domain requires uploading a
verification file to the server root. The file is provided by the WeChat admin.

- [ ] **Step 2: Verify HTTPS certificate**

```bash
ssh tencent 'echo | openssl s_client -connect api.doctoragentai.cn:443 -servername api.doctoragentai.cn 2>/dev/null | openssl x509 -noout -dates'
```

Expected: `notAfter` should be months in the future, not expired or expiring soon.

---

### Task 9: End-to-end miniapp QA (manual, on real device)

This task must be done on a real phone with the WeChat miniapp.

- [ ] **Step 1: Test invite code login**

Open the miniapp → enter a valid invite code → tap 登录.
Expected: WebView loads, doctor dashboard visible.

- [ ] **Step 2: Test chat**

Navigate to chat → send "你好".
Expected: AI responds within a few seconds.

- [ ] **Step 3: Test auth persistence**

Close the miniapp (swipe away) → reopen.
Expected: Dashboard loads directly, no login required.

- [ ] **Step 4: Test patient list**

Navigate to 患者 tab → scroll through list → tap a patient.
Expected: Patient detail loads with records.

- [ ] **Step 5: Test review queue**

Navigate to 审核 tab → check pending items.
Expected: Items load (or empty state if none pending).

- [ ] **Step 6: Test logout**

In settings → tap logout.
Expected: Returns to login page.

- [ ] **Step 7: Test network error**

Turn on airplane mode → try to load any page.
Expected: Error view with retry button. Turn off airplane mode → tap retry → page loads.

- [ ] **Step 8: Check visual issues**

On each page, verify:
- No horizontal scroll
- Bottom nav not hidden behind home indicator
- Chat input visible above keyboard when typing
- No content behind notch

Report any issues found.
