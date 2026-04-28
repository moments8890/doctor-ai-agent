# Staging Environment Implementation Plan

> **Visual version:** [2026-04-27-staging-environment.html](./2026-04-27-staging-environment.html) — diagram, task board, and side-by-side prod/staging architecture.
>
> Open in browser:
> file:///Volumes/ORICO/Code/doctor-ai-agent/docs/plans/2026-04-27-staging-environment.html

---

## TL;DR (read this first)

**What:** add a parallel pre-prod stack on the same Tencent CVM. Push to `gitee/staging` auto-deploys to staging server. Tag `v*-staging-*` uploads the miniapp to WeChat 开发版. Real users on 正式版 see byte-identical behavior to today.

**Why:** test WeChat miniapp + backend changes against real code without risking prod, before tagging a 正式版 release.

**Risk to public users:** zero functional change — the runtime resolver returns the prod URLs it returns today when `envVersion === "release"`. Public WeChat users cannot reach 开发版 (WeChat platform-side gating).

**Risk to prod infra:** non-zero — same kernel, disk, MySQL instance, network. Minimized via cgroup caps (`staging-build.slice`), per-branch deploy locks, and separate ports/schemas/paths. Residual risks (buffer-pool contention, instance outage, operator-error with wrong DSN) are explicit — escalate to dedicated CVM if any bite.

**Codex alignment:** 96%. Verdict: SHIP_THIS. Four review rounds, full history at the bottom.

---

## Reviewer's quick checklist

If you only have 10 minutes, read these five things in order:

1. **The mermaid diagram** ([Workflow Diagram section](#workflow-diagram)) — confirms the routing model is what you want.
2. **The `resolveBases()` snippet in Task 11** — this is the entire user-facing behavior change. ~15 lines. If this looks right, the rest is plumbing.
3. **The `webhook_server.py` rewrite in Task 3** — per-branch dispatch + per-branch locks. Confirms prod and staging deploys can't stomp each other.
4. **The two GitHub Actions workflows in Task 12** — confirms a misnamed tag can't ship the wrong bundle to the wrong slot.
5. **The "Decision points" table below** — three things you have to pick before execution.

---

## Decision points (you need to pick before we execute)

| # | Decision | Why we need it | Default if you don't say |
|---|----------|----------------|--------------------------|
| 1 | **MySQL password** for the `staging` MySQL user | Stored in `/etc/doctor-ai-staging.env` (root-owned 0600) on the CVM. Never in repo. | You generate one, paste into the CVM during Task 5 step 1 |
| 2 | **Tester WeChat IDs** to add to 开发版 access | These are the only WeChats that can scan the staging miniapp QR | Just yours, for now |
| 3 | **Same gitee remote** or new one for staging | Plan assumes existing `gitee` remote, branch `staging` | Same remote |

Two values are placeholders in the plan, intentional — fill them in at execution time, not now: `THE_REAL_PASSWORD` (3 occurrences), `wxABCDEF1234.txt` (the WeChat-issued verification filename, ~6 occurrences).

---

## Tasks at a glance

| # | Task | Type | Risk | Where |
|---|------|------|------|-------|
| 0 | Confirm prerequisites | Sanity | None | Laptop + SSH |
| 1 | DNS records (`app.stg` + `api.stg`) | Manual ops | None | Tencent CloudDNS console |
| 1b | Issue `*.stg.doctoragentai.cn` wildcard TLS cert | Manual ops (certbot) | None — new cert, doesn't touch prod | CVM |
| 2 | WeChat 后台 domain whitelist | Manual ops | None | mp.weixin.qq.com |
| 3 | Webhook server: per-branch dispatch + locks | Code (Python) | **Touches prod webhook** — restart required | Repo + CVM |
| 4 | Bootstrap staging working tree | Manual ops | None | SSH |
| 5 | MySQL schema + secret env file | Manual ops | Touches MySQL | SSH |
| 6 | nginx vhosts (api + app) | Code (nginx) | None — only adds new server blocks | Repo + CVM |
| 7 | systemd unit for staging backend | Code (systemd) | None — new unit | Repo + CVM |
| 8 | systemd slice for deploy-time caps | Code (systemd) | None — new slice | Repo + CVM |
| 9 | `deploy-staging.sh` (build-first ordering) | Code (bash) | None | Repo + CVM |
| 10 | Migrate 5 miniprogram pages off `runtimeConfig.apiBase` | Code (JS) | **Touches shipped JS** — review carefully | Repo |
| 11 | `resolveBases()` in `app.js` | Code (JS) | **Touches shipped JS** — this is THE user-facing change | Repo |
| 12 | CI tag guards (split workflows) | Code (CI) | Touches existing prod workflow | Repo |
| 13 | Wire gitee staging webhook | Manual ops | None | Gitee + CVM |
| 14 | First miniapp 开发版 upload | Manual + CI | None — lands in 开发版 only | Laptop + WeChat 后台 |
| 15 | Runbook | Code (docs) | None | Repo |
| 16 | Final verification (5-step smoke) | Manual | None | Multiple |

**Tasks that touch prod-adjacent surface (review these closely):** 3 (webhook), 10 (miniprogram pages), 11 (`app.js`), 12 (CI workflows). Everything else either creates new files or operates only on the staging side.

---

## Detailed sections

- [File Structure](#file-structure) — what the plan creates / modifies
- [Workflow Diagram](#workflow-diagram) — mermaid render of the full flow
- [Cascading Impact](#cascading-impact) — AGENTS-required impact analysis (all 9 categories)
- [Tasks 0-16](#task-0-confirm-prerequisites-and-clean-up-the-stale-plan-path) — bite-sized steps with verification
- [Rollback](#rollback) — undo path, ranked by surgical → aggressive
- [Open questions / known limitations](#open-questions--known-limitations) — what we know we don't know
- [Out of scope](#out-of-scope-flagged-for-follow-up) — flagged for later

---

## Files referenced in this plan

For quick navigation in your editor — open these alongside the plan as you read:

file:///Volumes/ORICO/Code/doctor-ai-agent/frontend/miniprogram/app.js

file:///Volumes/ORICO/Code/doctor-ai-agent/frontend/miniprogram/config.js

file:///Volumes/ORICO/Code/doctor-ai-agent/frontend/miniprogram/pages/doctor/doctor.js

file:///Volumes/ORICO/Code/doctor-ai-agent/frontend/miniprogram/pages/login/login.js

file:///Volumes/ORICO/Code/doctor-ai-agent/frontend/miniprogram/pages/voice/voice.js

file:///Volumes/ORICO/Code/doctor-ai-agent/frontend/miniprogram/pages/add-rule/add-rule.js

file:///Volumes/ORICO/Code/doctor-ai-agent/frontend/miniprogram/utils/api.js

file:///Volumes/ORICO/Code/doctor-ai-agent/deploy/tencent/deploy.sh

file:///Volumes/ORICO/Code/doctor-ai-agent/deploy/tencent/doctor-ai-backend.service

file:///Volumes/ORICO/Code/doctor-ai-agent/deploy/tencent/nginx/api.doctoragentai.cn.conf

file:///Volumes/ORICO/Code/doctor-ai-agent/deploy/tencent/nginx/app.doctoragentai.cn.conf

file:///Volumes/ORICO/Code/doctor-ai-agent/.github/workflows/miniprogram-release.yml

file:///Volumes/ORICO/Code/doctor-ai-agent/deploy/tencent/webhook_server.py

file:///Volumes/ORICO/Code/doctor-ai-agent/AGENTS.md

---

## Goal, Architecture, Risk

**Goal:** Add a parallel pre-prod stack on the same Tencent CVM as prod so we can test WeChat miniapp + backend changes against real code. WeChat 开发版 lands on staging; 正式版 stays exactly as it is today.

**Architecture:** Same CVM, two systemd backends (`:8000` prod, `:8001` staging), two nginx vhost pairs (`app.* / api.*` unchanged for prod, new `app.stg.* / api.stg.*` for staging), two MySQL schemas (`doctor_ai_prod`, `doctor_ai_staging`) on the same MySQL instance, two working trees driven by separate gitee branches. Same WeChat appid `wx9667f8091b342fb7`. The miniapp shell branches at runtime on `wx.getAccountInfoSync().miniProgram.envVersion` — `release` → prod URLs (unchanged), `develop`/`trial` → staging URLs.

**Tech Stack:** nginx, systemd (with slice for resource isolation), FastAPI, gitee webhook server (existing, will be revised), miniprogram-ci (existing, gated by branch-of-tag).

**Risk to prod (revised after Codex review):** Not zero. This is a **cheap pre-prod**, not an isolated staging environment. We share kernel, disk, MySQL instance, network, and deploy I/O with prod. We minimize that risk via:
- WeChat platform-side gating (only listed developers/testers can scan 开发版 QR)
- envVersion-driven runtime branch in the miniapp shell (`release` returns the same URLs it returns today)
- separate ports, schemas, working-tree paths
- a `staging-build.slice` cgroup that caps the staging deploy's RAM/CPU so a runaway `npm ci` cannot starve prod
- per-branch locking in the webhook server: prod and staging pushes run *in parallel* (each branch holds its own lock); two pushes to the *same* branch within one deploy window are de-duplicated (the second is skipped, not queued)

The residual risks (MySQL buffer-pool contention, IOPS spikes from concurrent migrations, instance-wide outage, operator error with the wrong DSN) are explicit; if any matter, escalate to a dedicated CVM.

---

## File Structure

**New files in repo:**
- `deploy/tencent/nginx/api.stg.doctoragentai.cn.conf` — staging API vhost (proxies to `:8001`)
- `deploy/tencent/nginx/app.stg.doctoragentai.cn.conf` — staging SPA vhost (serves staging dist)
- `deploy/tencent/doctor-ai-staging.service` — systemd unit for the staging backend
- `deploy/tencent/staging-build.slice` — cgroup for deploy-time resource caps
- `deploy/tencent/deploy-staging.sh` — staging deploy script (build-first ordering)
- `deploy/tencent/wx-verify/staging/.gitkeep` — placeholder; real `wx*.txt` lives here once issued by WeChat
- `.github/workflows/miniprogram-staging.yml` — CI for `v*-staging-*` tags, gated to `staging` branch
- `docs/deploy/staging.md` — runbook (canonical location per AGENTS.md docs table)

**Modified files in repo:**
- `frontend/miniprogram/app.js` — `resolveBases()` returns `{webBase, apiBase}`; populates both into `globalData`
- `frontend/miniprogram/config.example.js` — document new dual-base contract
- `frontend/miniprogram/pages/doctor/doctor.js:152, 237` — read `apiBase` from `app.globalData`, not `runtimeConfig`
- `frontend/miniprogram/pages/voice/voice.js:110` — same migration
- `frontend/miniprogram/pages/add-rule/add-rule.js:110, 181` — same migration
- `frontend/miniprogram/pages/login/login.js:28` — switch to `webBase` for the WebView src
- `frontend/miniprogram/pages/doctor/doctor.js:36` — switch to `webBase` for the WebView src
- `frontend/miniprogram/utils/api.js:7` — read `apiBase` from `app.globalData` (already does, but clarify)
- `deploy/tencent/webhook_server.py` — branch-aware dispatch with per-branch locks
- `.github/workflows/miniprogram-release.yml` — gate to `main` branch only; rename context-clear

**Manual one-time changes (outside repo):**
- DNS: `app.stg` and `api.stg` A records on Tencent CloudDNS → CVM public IP
- WeChat 后台 → 开发管理 → 开发设置 → 服务器域名: add `https://api.stg.doctoragentai.cn` to `request合法域名`, add `https://app.stg.doctoragentai.cn` to `业务域名`. WeChat will issue a `wx*.txt` verification file — drop into `deploy/tencent/wx-verify/staging/`
- CVM bootstrap: working tree, MySQL schema, secret env file, systemd unit, slice
- Gitee: create `staging` branch
- WeChat 后台 → 成员管理 → 体验成员: add testers' WeChat IDs

---

## Workflow Diagram

```mermaid
flowchart TB
  subgraph Dev["Developer laptop"]
    DevTools["WeChat devtools<br/>(uses config.js LAN URL)"]
  end

  subgraph Phones["Phones in WeChat"]
    Tester["Tester WeChat<br/>(listed in 后台)"]
    User["Public user WeChat"]
  end

  subgraph WeChat["WeChat platform"]
    DevSlot["开发版 slot<br/>envVersion=develop"]
    ProdSlot["正式版 slot<br/>envVersion=release"]
  end

  subgraph CI["CI (GitHub Actions)"]
    StagingWF["miniprogram-staging.yml<br/>tag v*-staging-*<br/>guard: on staging branch"]
    ProdWF["miniprogram-release.yml<br/>tag v*<br/>guard: on main branch"]
  end

  subgraph CVM["Tencent CVM (single host)"]
    Webhook["webhook_server.py<br/>per-branch locks"]
    subgraph Slice["staging-build.slice cgroup<br/>4G RAM, 200% CPU, no swap"]
      DeployS["deploy-staging.sh<br/>build → migrate → restart"]
    end
    DeployP["deploy.sh (prod, unchanged)"]

    subgraph ProdStack["Prod stack"]
      ProdNginx["nginx<br/>app.* + api.*"]
      ProdSvc["doctor-ai-backend :8000"]
      ProdDB[(doctor_ai_prod)]
    end
    subgraph StgStack["Staging stack"]
      StgNginx["nginx<br/>app.stg.* + api.stg.*"]
      StgSvc["doctor-ai-staging :8001<br/>EnvironmentFile=/etc/doctor-ai-staging.env"]
      StgDB[(doctor_ai_staging)]
      WXVerify["wx-verify/staging/wx*.txt<br/>(static, outside dist)"]
    end

    MySQL["MySQL :3306 (shared instance)"]
  end

  subgraph Gitee["Gitee"]
    Main["main branch"]
    Staging["staging branch"]
  end

  DevTools -->|LAN dev| StgNginx
  Tester -->|tap 开发版 QR| DevSlot
  User -->|tap public icon| ProdSlot
  DevSlot -->|WebView| StgNginx
  DevSlot -->|wx.request| StgNginx
  ProdSlot -->|WebView| ProdNginx
  ProdSlot -->|wx.request| ProdNginx
  StgNginx --> StgSvc
  StgNginx --> WXVerify
  ProdNginx --> ProdSvc
  StgSvc --> MySQL
  ProdSvc --> MySQL
  MySQL --- StgDB
  MySQL --- ProdDB

  Main -->|push| Webhook
  Staging -->|push| Webhook
  Staging -->|tag v*-staging-*| StagingWF
  Main -->|tag v*| ProdWF
  Webhook -->|"branch=main"| DeployP
  Webhook -->|"branch=staging"| DeployS
  DeployP --> ProdSvc
  DeployS --> StgSvc
  StagingWF -->|miniprogram-ci upload| DevSlot
  ProdWF -->|miniprogram-ci upload<br/>then human submits 审核| ProdSlot
```

The diagram makes the runtime gating explicit: *which slot the WeChat user opens* decides which CVM stack their phone talks to, with the runtime `resolveBases()` doing the routing once inside the bundle.

---

## Cascading Impact

Per AGENTS.md:240. Every category enumerated, even where the answer is "None":

1. **DB schema** — None. Staging gets a separate MySQL schema (`doctor_ai_staging`) populated by the existing alembic chain. No new tables/columns introduced by this plan; staging schema mirrors prod.
2. **ORM models & Pydantic schemas** — None. No model changes.
3. **API endpoints** — None. No new routes, no shape changes. The staging backend serves the existing FastAPI app verbatim against a different DB.
4. **Domain logic** — None. The backend code is unchanged; staging just runs it against a different DSN.
5. **Prompt files** — None. Prompts are loaded from disk identically in both environments.
6. **Frontend** — `frontend/miniprogram/app.js` (split `apiBase` → `webBase` + `apiBase`). 5 page-level call sites migrate from `runtimeConfig.apiBase` to `app.globalData.apiBase` (Task 10). 2 WebView-src readers migrate from `app.globalData.apiBase` to `app.globalData.webBase` (Task 11 step 3). The browser-side React SPA is **not** touched — its API base is set at build time via `VITE_API_BASE_URL` per workflow.
7. **Configuration** — New env file `/etc/doctor-ai-staging.env` (root-owned 0600, NOT in repo). New webhook env vars `DEPLOY_SCRIPT_MAIN`, `DEPLOY_SCRIPT_STAGING`. New systemd unit `doctor-ai-staging.service`. New systemd slice `staging-build.slice`. Two new GitHub Actions workflows. No `runtime.json` changes.
8. **Existing tests** — None expected to break. The miniprogram has no unit tests today; manual QA covers the WebView smoke test. Backend tests already use `ENVIRONMENT=test` / throwaway DB and are not affected.
9. **Cleanup** — Stale `docs/superpowers/plans/2026-04-27-staging-environment.md` is deleted as part of this plan (already done in Task 0 below). The repo's `frontend/miniprogram/config.js` LAN-IP comment is updated to reflect the new dual-base contract (Task 11 step 2).

---

## Task 0: Confirm prerequisites and clean up the stale plan path

**Type:** Sanity gate before any infra changes.

- [ ] **Step 1: Confirm the deprecated plan file is gone**

```bash
ls /Volumes/ORICO/Code/doctor-ai-agent/docs/superpowers/plans/2026-04-27-staging-environment.md 2>/dev/null \
  && echo "STILL EXISTS — delete it" \
  || echo "OK — already removed"
```
Expected: `OK — already removed`. If not, `rm` it before continuing.

- [ ] **Step 2: Confirm CVM Python and node versions**

The webhook server runs on Python 3.9+ (system Python on Ubuntu 22.04). The deploy uses node 20 via `npm`. SSH to CVM and confirm:
```bash
ssh ubuntu@CVM "python3 --version && node --version"
```
Expected: Python ≥ 3.9, node ≥ 20. If lower, the type annotations and JS features used in this plan will fail.

---

## Task 1: DNS records

**Type:** Manual ops (Tencent CloudDNS)

- [ ] **Step 1: Add two A records**

In Tencent CloudDNS for `doctoragentai.cn`:
- `app.stg` A → CVM public IP (same as `app`)
- `api.stg` A → CVM public IP (same as `api`)

(Multi-level subdomains work fine on DNS — `app.stg.doctoragentai.cn` is just two levels deep. We use specific records, not a `*.stg` wildcard, so unintended hosts don't auto-resolve.)

- [ ] **Step 2: Verify propagation**

```bash
dig +short app.stg.doctoragentai.cn
dig +short api.stg.doctoragentai.cn
dig +short app.doctoragentai.cn   # for comparison — must match
```
All three must return the CVM public IP.

---

## Task 1b: Issue `*.stg.doctoragentai.cn` wildcard TLS cert

**Type:** Manual ops (one-time, ~5 min via certbot DNS-01).

**Why a new cert:** the existing `*.doctoragentai.cn` cert is single-level, so it does NOT cover `app.stg.doctoragentai.cn` or `api.stg.doctoragentai.cn` (those are two labels deep). We issue a second wildcard cert for `*.stg.doctoragentai.cn` and reference it from the staging vhosts only. Prod vhosts keep using the existing wildcard.

- [ ] **Step 1: Confirm DNS-01 plugin auth**

The existing prod cert is presumably renewed via certbot DNS-01 (Tencent CloudDNS plugin or webroot). Confirm the same mechanism is set up on the CVM:
```bash
ssh ubuntu@CVM "ls /etc/letsencrypt/live/ && sudo certbot certificates 2>&1 | head -30"
```
Expected: existing `doctoragentai.cn` cert with `*.doctoragentai.cn` SAN, and a renewal hook.

- [ ] **Step 2: Issue the new wildcard cert**

```bash
sudo certbot certonly \
  --dns-tencentcloud \
  --dns-tencentcloud-credentials /etc/letsencrypt/tencentcloud.ini \
  --cert-name stg.doctoragentai.cn \
  -d "*.stg.doctoragentai.cn" \
  --agree-tos --no-eff-email --non-interactive
```

(Substitute the actual DNS plugin and credentials path your existing cert uses. If you use the `manual` plugin, certbot will print a TXT record to add to Tencent CloudDNS for `_acme-challenge.stg`.)

Expected: cert lands at `/etc/letsencrypt/live/stg.doctoragentai.cn/fullchain.pem` + `privkey.pem`.

- [ ] **Step 3: Symlink into nginx cert directory**

```bash
sudo mkdir -p /etc/nginx/certs
sudo ln -sf /etc/letsencrypt/live/stg.doctoragentai.cn/fullchain.pem \
            /etc/nginx/certs/wildcard.stg.doctoragentai.cn.crt
sudo ln -sf /etc/letsencrypt/live/stg.doctoragentai.cn/privkey.pem \
            /etc/nginx/certs/wildcard.stg.doctoragentai.cn.key
ls -l /etc/nginx/certs/wildcard.stg.*
```
Expected: two symlinks pointing at the live certbot files.

- [ ] **Step 4: Verify cert covers both staging hosts**

```bash
sudo openssl x509 -in /etc/nginx/certs/wildcard.stg.doctoragentai.cn.crt -noout -ext subjectAltName
```
Expected output includes `DNS:*.stg.doctoragentai.cn`.

- [ ] **Step 5: Confirm certbot renewal hook reloads nginx**

The existing renewal hook should already reload nginx for any cert. Confirm:
```bash
sudo cat /etc/letsencrypt/renewal-hooks/deploy/*.sh 2>/dev/null
```
If it doesn't exist, add one:
```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
systemctl reload nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

This way, when the `*.stg.doctoragentai.cn` cert renews 90 days from now, nginx picks it up automatically.

---

## Task 2: WeChat 后台 domain whitelist

**Type:** Manual ops (mp.weixin.qq.com)

- [ ] **Step 1: Add staging domains**

Log in as appid `wx9667f8091b342fb7` → 开发管理 → 开发设置 → 服务器域名 → 修改:
- **request合法域名:** add `https://api.stg.doctoragentai.cn`
- **业务域名:** add `https://app.stg.doctoragentai.cn`
- Keep all existing entries.

- [ ] **Step 2: Save the verification file**

WeChat issues a file like `wxABCDEF1234.txt` for the 业务域名 step. Download it. Save it locally.

- [ ] **Step 3: Commit it to the repo at a stable path**

```bash
mkdir -p /Volumes/ORICO/Code/doctor-ai-agent/deploy/tencent/wx-verify/staging
mv ~/Downloads/wxABCDEF1234.txt /Volumes/ORICO/Code/doctor-ai-agent/deploy/tencent/wx-verify/staging/
git add deploy/tencent/wx-verify/staging/wxABCDEF1234.txt
git commit -m "chore(staging): add WeChat 业务域名 verification file"
```

The nginx vhost in Task 6 serves this directly out of the working tree, NOT out of `dist`, so it survives every deploy without find/cp games.

---

## Task 3: Revise webhook server for per-branch dispatch with per-branch locks

**Files:**
- Modify: `deploy/tencent/webhook_server.py`

**Why this comes first:** Once `staging` branch exists on gitee and a webhook is configured, the existing `webhook_server.py` would happily run prod's `deploy.sh` for staging pushes (it ignores `ref`). Fix the dispatcher *before* anything else can trigger it.

- [ ] **Step 1: Replace `webhook_server.py`**

Open `deploy/tencent/webhook_server.py` and replace the dispatch section so it picks the deploy script by branch and uses per-branch locks. Full file:

```python
#!/usr/bin/env python3
"""
webhook_server.py — Gitee Webhook 监听服务

监听端口：9000（由 nginx 代理 /hooks/deploy → 127.0.0.1:9000）
分发规则：根据 push payload 的 ref 字段选择对应分支的 deploy 脚本
并发保护：每个分支独立持有一把锁；同分支重复请求跳过；不同分支请求并行。

Python 3.9 compatible per AGENTS.md:120 — no `list[str]` / `str | None`,
typing imports only.
"""
from __future__ import annotations

import hmac
import http.server
import json
import logging
import os
import subprocess
import threading
from typing import Dict, List, Optional

PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
SECRET = os.environ.get("WEBHOOK_SECRET", "")

# Branch → deploy command. The staging command runs under a systemd slice so
# its RAM/CPU is capped and cannot starve prod. Slice unit lives at
# /etc/systemd/system/staging-build.slice (see Task 8).
BRANCH_DEPLOYS: Dict[str, List[str]] = {
    "main": [
        "/bin/bash",
        os.environ.get("DEPLOY_SCRIPT_MAIN", "/home/ubuntu/deploy.sh"),
    ],
    "staging": [
        "/usr/bin/systemd-run",
        "--unit=staging-deploy-%s" % os.getpid(),
        "--slice=staging-build.slice",
        "--collect",
        "--wait",
        "--quiet",
        "/bin/bash",
        os.environ.get("DEPLOY_SCRIPT_STAGING", "/home/ubuntu/deploy-staging.sh"),
    ],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("webhook")

# One lock per branch — main and staging deploys can run concurrently;
# two pushes to the same branch within one deploy window queue (skip).
_locks: Dict[str, threading.Lock] = {b: threading.Lock() for b in BRANCH_DEPLOYS}


def _run_deploy(branch: str, command: List[str]) -> None:
    lock = _locks[branch]
    if not lock.acquire(blocking=False):
        log.warning("deploy already in progress for %s — skipping", branch)
        return
    try:
        log.info("starting %s deploy: %s", branch, " ".join(command))
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min — npm ci on cold cache ~3 min, plus headroom
        )
        if result.returncode == 0:
            log.info("%s deploy succeeded:\n%s", branch, result.stdout[-2000:])
        else:
            log.error(
                "%s deploy failed (rc=%d):\n%s\n%s",
                branch,
                result.returncode,
                result.stdout[-1000:],
                result.stderr[-1000:],
            )
    except subprocess.TimeoutExpired:
        log.error("%s deploy timed out after 15 min", branch)
    except Exception as exc:
        log.exception("%s deploy error: %s", branch, exc)
    finally:
        lock.release()


def _branch_from_ref(ref: str) -> Optional[str]:
    # gitee sends e.g. "refs/heads/main" or "refs/heads/staging"
    prefix = "refs/heads/"
    if ref.startswith(prefix):
        return ref[len(prefix):]
    return None


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        if self.path not in ("/hooks/deploy", "/hooks/deploy/"):
            self._reply(404, "not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        token = self.headers.get("X-Gitee-Token", "")
        if SECRET and not hmac.compare_digest(token, SECRET):
            log.warning("invalid token from %s", self.client_address[0])
            self._reply(401, "unauthorized")
            return

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}

        ref = payload.get("ref", "")
        branch = _branch_from_ref(ref)
        log.info("push event ref=%r (branch=%r) from %s", ref, branch, self.client_address[0])

        command = BRANCH_DEPLOYS.get(branch) if branch else None
        if not command:
            log.info("ignoring push to unknown branch %r", branch)
            self._reply(200, "ignored: unknown branch")
            return

        threading.Thread(
            target=_run_deploy, args=(branch, command), daemon=True
        ).start()
        self._reply(200, f"deploying {branch}")

    def _reply(self, code: int, msg: str):
        body = (msg + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if not SECRET:
        log.warning("WEBHOOK_SECRET is not set — all requests will be accepted")
    BIND = os.environ.get("WEBHOOK_BIND", "127.0.0.1")
    server = http.server.ThreadingHTTPServer((BIND, PORT), WebhookHandler)
    log.info("webhook server listening on %s:%d (branches: %s)",
             BIND, PORT, ", ".join(BRANCH_DEPLOYS.keys()))
    server.serve_forever()
```

- [ ] **Step 2: Sanity-check the diff**

Differences from the prior file:
1. `BRANCH_DEPLOYS` dict replaces single `DEPLOY_SCRIPT` env var.
2. `_locks` is a dict keyed by branch — concurrent prod + staging serialize *within* a branch only.
3. `_branch_from_ref` parses `refs/heads/<x>` and rejects unknown branches with `200 ignored`.
4. Staging command runs under `systemd-run --slice=staging-build.slice` to put the deploy in a cgroup.
5. Timeout is 900s (15 min) — the prior 120s value would kill `npm ci` on cold cache.

- [ ] **Step 3: Commit**

```bash
git add deploy/tencent/webhook_server.py
git commit -m "feat(deploy): branch-aware webhook dispatch with per-branch locks"
```

- [ ] **Step 4: Deploy on the CVM after main deploy script lands**

The webhook unit runs from a path on the CVM. After the next prod deploy lands this commit, restart the webhook unit:
```bash
ssh ubuntu@CVM
sudo systemctl restart doctor-ai-webhook
sudo journalctl -u doctor-ai-webhook -n 20
```
Expected: log line `webhook server listening on 127.0.0.1:9000 (branches: main, staging)`.

---

## Task 4: Bootstrap staging working tree

**Type:** Manual ops (one-time SSH)

- [ ] **Step 1: Create gitee staging branch (laptop)**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
git checkout -b staging main
git push gitee staging
git checkout main
```

- [ ] **Step 2: Clone tree on CVM**

```bash
ssh ubuntu@CVM
cd /home/ubuntu
git clone -b staging git@gitee.com:moments8890/doctor-ai-agent.git doctor-ai-staging
cd doctor-ai-staging
git remote add github git@github.com:moments8890/doctor-ai-agent.git
```

- [ ] **Step 3: Create venv + dirs**

```bash
cd /home/ubuntu/doctor-ai-staging
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
mkdir -p logs uploads
```

---

## Task 5: Create staging MySQL schema and secret env file

**Type:** Manual ops (one-time SSH; secrets stay on the CVM, never in repo)

- [ ] **Step 1: Create empty schema**

```bash
ssh ubuntu@CVM
mysql -u root -p <<'SQL'
CREATE DATABASE doctor_ai_staging
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'staging'@'localhost' IDENTIFIED BY 'PUT_REAL_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON doctor_ai_staging.* TO 'staging'@'localhost';
FLUSH PRIVILEGES;
SQL
```

Pick a real password. Save in your password manager.

- [ ] **Step 2: Create the secret env file (root-owned, 0600)**

```bash
sudo tee /etc/doctor-ai-staging.env >/dev/null <<EOF
DATABASE_URL=mysql+pymysql://staging:THE_REAL_PASSWORD@localhost/doctor_ai_staging
ENVIRONMENT=staging
PYTHONPATH=/home/ubuntu/doctor-ai-staging/src
EOF
sudo chown root:root /etc/doctor-ai-staging.env
sudo chmod 0600 /etc/doctor-ai-staging.env
ls -l /etc/doctor-ai-staging.env
```
Expected: `-rw------- 1 root root ... /etc/doctor-ai-staging.env`. Systemd will read this via `EnvironmentFile=`; the file does not appear in any process listing or unit file.

- [ ] **Step 3: Run alembic migrations**

Use `systemd-run --property=EnvironmentFile=` so the DSN never appears in `ps`/`/proc/<pid>/cmdline` and is loaded directly from the 0600 file by systemd. (The earlier `env $(... | xargs)` pattern leaks the DSN into the process arg list and breaks on values with spaces or quotes.)

```bash
cd /home/ubuntu/doctor-ai-staging
sudo systemd-run --pty --quiet --collect \
  --uid=ubuntu \
  --working-directory=/home/ubuntu/doctor-ai-staging \
  --property=EnvironmentFile=/etc/doctor-ai-staging.env \
  /home/ubuntu/doctor-ai-staging/.venv/bin/alembic upgrade head
```
Expected: alembic walks to head with no errors. (The `systemd-run` invocation creates a transient unit that reads the env file with the same secrecy guarantees as the long-running unit.)

If `--property=EnvironmentFile=` is unsupported on the CVM's systemd version, fallback (still safe — `set -a; source` keeps env values out of `ps`):
```bash
cd /home/ubuntu/doctor-ai-staging
sudo bash -c 'set -a; source /etc/doctor-ai-staging.env; set +a; sudo -u ubuntu --preserve-env=DATABASE_URL,ENVIRONMENT,PYTHONPATH .venv/bin/alembic upgrade head'
```

- [ ] **Step 4: Seed minimum data**

```bash
cd /home/ubuntu/doctor-ai-staging
sudo systemd-run --pty --quiet --collect \
  --uid=ubuntu \
  --working-directory=/home/ubuntu/doctor-ai-staging \
  --property=EnvironmentFile=/etc/doctor-ai-staging.env \
  /home/ubuntu/doctor-ai-staging/.venv/bin/python scripts/ensure_welcome_code.py
```

---

## Task 6: nginx vhosts (api + app) with stable WeChat-verify path

**Files:**
- Create: `deploy/tencent/nginx/api.stg.doctoragentai.cn.conf`
- Create: `deploy/tencent/nginx/app.stg.doctoragentai.cn.conf`

- [ ] **Step 1: Write `api.stg.doctoragentai.cn.conf`**

```nginx
# api.stg.doctoragentai.cn — staging FastAPI on :8001.
# Mirror of api.* — same TLS cert, different upstream port.
# 正式版 miniapp can NEVER reach this (WeChat domain whitelist gating + envVersion routing).

server {
    listen 80;
    listen [::]:80;
    server_name api.stg.doctoragentai.cn;
    location /.well-known/acme-challenge/ { root /var/www/certbot; try_files $uri =404; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.stg.doctoragentai.cn;

    ssl_certificate     /etc/nginx/certs/wildcard.stg.doctoragentai.cn.crt;
    ssl_certificate_key /etc/nginx/certs/wildcard.stg.doctoragentai.cn.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 1d;
    server_tokens off;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    # No HSTS on staging — keeps the browser from pinning a misconfigured cert.

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
```

- [ ] **Step 2: Write `app.stg.doctoragentai.cn.conf`**

```nginx
# app.stg.doctoragentai.cn — staging SPA. Static-only.
# WeChat 业务域名 verification file is served from the working tree, NOT from
# dist — survives every deploy without copy/find games.

server {
    listen 80;
    listen [::]:80;
    server_name app.stg.doctoragentai.cn;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name app.stg.doctoragentai.cn;

    ssl_certificate     /etc/nginx/certs/wildcard.stg.doctoragentai.cn.crt;
    ssl_certificate_key /etc/nginx/certs/wildcard.stg.doctoragentai.cn.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    server_tokens off;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    # No HSTS on staging.

    add_header Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self' https://res.wx.qq.com 'unsafe-inline'; connect-src 'self' https://api.stg.doctoragentai.cn; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'" always;

    client_max_body_size 20m;

    # WeChat 业务域名 verification — served from a stable path outside `dist`.
    # alias resolves the matched filename to deploy/tencent/wx-verify/staging/<name>.txt
    # Deploys do not touch this directory.
    location ~ ^/(wx[A-Za-z0-9_]+\.txt)$ {
        alias /home/ubuntu/doctor-ai-staging/deploy/tencent/wx-verify/staging/$1;
        try_files "" =404;
        default_type text/plain;
    }

    root /home/ubuntu/doctor-ai-staging/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 3: Symlink + reload**

```bash
sudo ln -sf /home/ubuntu/doctor-ai-agent/deploy/tencent/nginx/api.stg.doctoragentai.cn.conf /etc/nginx/sites-enabled/
sudo ln -sf /home/ubuntu/doctor-ai-agent/deploy/tencent/nginx/app.stg.doctoragentai.cn.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

- [ ] **Step 4: Verify WX-verify file is reachable**

After Task 2 step 3, the file is in the staging working tree. Test:
```bash
curl -s https://app.stg.doctoragentai.cn/wxABCDEF1234.txt
```
Expected: returns the verification token WeChat issued. (If you haven't done the WeChat 后台 step yet, this will be a 404 — that's fine, do Task 2 then come back.)

- [ ] **Step 5: Commit**

```bash
git add deploy/tencent/nginx/api.stg.doctoragentai.cn.conf
git add deploy/tencent/nginx/app.stg.doctoragentai.cn.conf
git commit -m "feat(staging): nginx vhosts for api.stg and app.stg"
```

---

## Task 7: systemd unit for staging backend (with EnvironmentFile)

**Files:**
- Create: `deploy/tencent/doctor-ai-staging.service`

- [ ] **Step 1: Write the unit file**

```ini
[Unit]
Description=doctor-ai-agent staging backend (cli.py --prod, :8001)
After=network.target docker.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/doctor-ai-staging
EnvironmentFile=/etc/doctor-ai-staging.env
ExecStart=/home/ubuntu/doctor-ai-staging/.venv/bin/python /home/ubuntu/doctor-ai-staging/cli.py start --prod --no-frontend --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5

# Cap the running unit so a runaway staging process can't starve prod.
# Note: this only covers the long-running FastAPI process. Deploy-time
# spikes (npm ci, pip install, vite build) are capped separately by
# staging-build.slice (Task 8).
MemoryMax=2G
CPUQuota=150%

StandardOutput=append:/home/ubuntu/doctor-ai-staging/logs/backend.log
StandardError=append:/home/ubuntu/doctor-ai-staging/logs/backend.log

[Install]
WantedBy=multi-user.target
```

No password in this file. The `EnvironmentFile=/etc/doctor-ai-staging.env` (Task 5 step 2) is root-owned 0600.

- [ ] **Step 2: Install + enable**

```bash
sudo cp /home/ubuntu/doctor-ai-agent/deploy/tencent/doctor-ai-staging.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable doctor-ai-staging
```
Don't start yet — needs the dist build from Task 9.

- [ ] **Step 3: Commit**

```bash
git add deploy/tencent/doctor-ai-staging.service
git commit -m "feat(staging): systemd unit (with EnvironmentFile, capped resources)"
```

---

## Task 8: systemd slice for deploy-time resource caps

**Files:**
- Create: `deploy/tencent/staging-build.slice`

- [ ] **Step 1: Write the slice unit**

```ini
[Unit]
Description=Staging build/deploy resource cap

[Slice]
# Cover the entire deploy: pip install, npm ci, vite build, alembic, etc.
# These are the workloads that historically OOM. Capping the slice (not
# the unit) puts every transient process spawned via `systemd-run --slice=...`
# under the same cgroup, so the deploy itself can't push prod into swap.
MemoryMax=4G
MemorySwapMax=0
CPUQuota=200%
TasksMax=4096
```

- [ ] **Step 2: Install**

```bash
sudo cp /home/ubuntu/doctor-ai-agent/deploy/tencent/staging-build.slice /etc/systemd/system/
sudo systemctl daemon-reload
```

The slice doesn't need `enable`; it's instantiated when something joins it via `systemd-run --slice=staging-build.slice`. Verify:
```bash
systemctl show staging-build.slice -p MemoryMax,CPUQuotaPerSecUSec
```

- [ ] **Step 3: Commit**

```bash
git add deploy/tencent/staging-build.slice
git commit -m "feat(staging): cgroup slice caps for deploy-time RAM/CPU"
```

---

## Task 9: deploy-staging.sh (build-first ordering)

**Files:**
- Create: `deploy/tencent/deploy-staging.sh`

**Why the order matters:** Codex flagged that the prod deploy script runs `git reset → pip install → alembic upgrade → npm build → restart`. If `npm build` OOMs after alembic ran, the running service is on old code but the DB is on the new schema. For staging this is survivable, but the cure is ~free: build first, migrate second, restart third. Then a build failure leaves the previous deploy running on the previous schema.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# deploy-staging.sh — staging deploy.
# Invocation: webhook calls this via systemd-run --slice=staging-build.slice
# so resource usage is capped at the cgroup level (see Task 8).
#
# Ordering (intentionally different from prod's deploy.sh):
#   1. git reset
#   2. pip install         } harmless, idempotent
#   3. npm ci + vite build } the most likely thing to OOM — do it BEFORE alembic
#   4. alembic upgrade head
#   5. atomic dist swap
#   6. restart unit
#
# A build failure at step 3 aborts the script; service keeps serving old
# code on old schema. No mixed state.
set -euo pipefail

APP_DIR="/home/ubuntu/doctor-ai-staging"
VENV="$APP_DIR/.venv"
LOG="$APP_DIR/logs/deploy.log"
ENV_FILE="/etc/doctor-ai-staging.env"

exec >> "$LOG" 2>&1
echo "=== staging deploy started at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

cd "$APP_DIR"

# 1. Pull latest staging branch.
git fetch origin
git reset --hard origin/staging

GIT_COMMIT=$(git rev-parse HEAD)
sudo mkdir -p /etc/systemd/system/doctor-ai-staging.service.d
sudo tee /etc/systemd/system/doctor-ai-staging.service.d/release.conf >/dev/null <<EOF
[Service]
Environment=GIT_COMMIT=${GIT_COMMIT}
EOF
sudo systemctl daemon-reload

# 2. Python deps (idempotent).
"$VENV/bin/pip" install -q -r requirements.txt

# 3. Build frontend FIRST. If this OOMs, exit before touching DB.
cd "$APP_DIR/frontend/web"
npm ci --silent
VITE_API_BASE_URL=https://api.stg.doctoragentai.cn npm run build

# 4. Now run migrations (env loaded from EnvironmentFile-equivalent).
set -a
source "$ENV_FILE"
set +a
cd "$APP_DIR"
"$VENV/bin/alembic" upgrade head

# 5. Atomic dist swap. We do NOT ship the WeChat-verify TXT through dist —
# nginx serves it directly out of deploy/tencent/wx-verify/staging/ (Task 6).
NEW_DIST="$APP_DIR/frontend/dist.new.$$"
OLD_DIST="$APP_DIR/frontend/dist.old.$$"
rm -rf "$NEW_DIST" "$OLD_DIST" 2>/dev/null || true
cp -r "$APP_DIR/frontend/web/dist" "$NEW_DIST"
chmod -R o+rX "$NEW_DIST"
[ -e "$APP_DIR/frontend/dist" ] && mv "$APP_DIR/frontend/dist" "$OLD_DIST"
mv "$NEW_DIST" "$APP_DIR/frontend/dist"
rm -rf "$OLD_DIST" 2>/dev/null || true

# 6. Bytecode bust + restart.
find "$APP_DIR/src" -type d -name __pycache__ -prune -exec rm -rf {} +
sudo systemctl restart doctor-ai-staging

echo "=== staging deploy finished at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
```

- [ ] **Step 2: Make executable + symlink (CVM)**

```bash
chmod +x /home/ubuntu/doctor-ai-agent/deploy/tencent/deploy-staging.sh
sudo ln -sf /home/ubuntu/doctor-ai-agent/deploy/tencent/deploy-staging.sh /home/ubuntu/deploy-staging.sh
```

- [ ] **Step 3: Sudoers for the staging service**

```bash
sudo tee -a /etc/sudoers.d/ubuntu-deploy >/dev/null <<'EOF'
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart doctor-ai-staging
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl daemon-reload
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/systemd/system/doctor-ai-staging.service.d/release.conf
ubuntu ALL=(ALL) NOPASSWD: /bin/mkdir -p /etc/systemd/system/doctor-ai-staging.service.d
EOF
sudo visudo -c
```

- [ ] **Step 4: First manual run + verify**

```bash
sudo systemd-run --slice=staging-build.slice --collect --wait --quiet \
  /bin/bash /home/ubuntu/deploy-staging.sh
tail -60 /home/ubuntu/doctor-ai-staging/logs/deploy.log
```
Expected: log ends with `staging deploy finished`.

```bash
sudo systemctl status doctor-ai-staging
curl -s http://127.0.0.1:8001/healthz
curl -sI https://app.stg.doctoragentai.cn/ | head -3
```
Expected: unit active, healthz `{"ok":true}`, SPA returns `HTTP/2 200`.

- [ ] **Step 5: Commit**

```bash
git add deploy/tencent/deploy-staging.sh
git commit -m "feat(staging): deploy-staging.sh with build-first ordering"
```

---

## Task 10: Migrate miniprogram pages off `runtimeConfig.apiBase`

**Why this is a must-fix (Codex finding #1):** `app.globalData.apiBase` is the resolved-at-runtime value the miniapp shell computes. But 5 page-level call sites bypass it and read `runtimeConfig.apiBase` directly. Those reads short-circuit our envVersion branch — they would always hit the LAN dev URL on real phones (or whatever the literal `config.js` value is). Codex called this out at:
- `frontend/miniprogram/pages/doctor/doctor.js:152`
- `frontend/miniprogram/pages/doctor/doctor.js:237`
- `frontend/miniprogram/pages/voice/voice.js:110`
- `frontend/miniprogram/pages/add-rule/add-rule.js:110`
- `frontend/miniprogram/pages/add-rule/add-rule.js:181`

This task migrates all five.

**Files:** the five above.

- [ ] **Step 1: `pages/doctor/doctor.js`**

Find:
```js
url: runtimeConfig.apiBase + "/api/voice/session?doctor_id=" + encodeURIComponent(doctorId),
```
Replace with:
```js
url: app.globalData.apiBase + "/api/voice/session?doctor_id=" + encodeURIComponent(doctorId),
```

Find:
```js
url: runtimeConfig.apiBase + "/api/voice/session",
```
Replace with:
```js
url: app.globalData.apiBase + "/api/voice/session",
```

Keep `runtimeConfig.subscribeTemplateId` as-is — that field is unrelated.

Confirm `const app = getApp();` already exists at the top of the page (it does, see line 36).

- [ ] **Step 2: `pages/voice/voice.js`**

Find:
```js
const apiBase = runtimeConfig.apiBase;
```
Replace with:
```js
const app = getApp();
const apiBase = app.globalData.apiBase;
```
(or inline at the use site if cleaner).

- [ ] **Step 3: `pages/add-rule/add-rule.js`**

Find both:
```js
url: `${config.apiBase}/api/manage/knowledge/voice-extract?doctor_id=${encodeURIComponent(doctorId)}`,
```
```js
url: `${config.apiBase}/api/manage/knowledge?doctor_id=${encodeURIComponent(doctorId)}`,
```
Replace `${config.apiBase}` with `${getApp().globalData.apiBase}` in both. Remove the `const config = require(...)` import if it's only used for `apiBase`.

- [ ] **Step 4: Grep to confirm zero direct reads remain**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
grep -rn "runtimeConfig.apiBase\|config.apiBase" frontend/miniprogram/ \
  --include="*.js" --include="*.wxml"
```
Expected: only `app.js` matches (legitimate — it's the resolver source). All page-level matches gone.

- [ ] **Step 5: Commit**

```bash
git add frontend/miniprogram/pages/doctor/doctor.js
git add frontend/miniprogram/pages/voice/voice.js
git add frontend/miniprogram/pages/add-rule/add-rule.js
git commit -m "refactor(miniprogram): page-level requests use app.globalData.apiBase"
```

---

## Task 11: `resolveBases()` in app.js — split webBase and apiBase

**Why this is a must-fix (Codex finding #1):** the prod nginx tells us `app.doctoragentai.cn` has **no `/api/` proxy** (see `deploy/tencent/nginx/app.doctoragentai.cn.conf` header comment). The SPA fetches the API from `api.doctoragentai.cn` cross-origin. So the miniapp must distinguish between:
- the **WebView URL** (point at `app.*` / `app.stg.*`)
- the **API base URL** (point at `api.*` / `api.stg.*`)

Today the miniapp uses one field for both, papering over it with a bare-domain fallback. We make the split explicit.

**Files:** `frontend/miniprogram/app.js`, `frontend/miniprogram/config.example.js`, plus the WebView-src readers (`pages/doctor/doctor.js:36`, `pages/login/login.js:28`).

- [ ] **Step 1: Replace `app.js` content**

```js
const runtimeConfig = require("./config.js");

// Resolve {webBase, apiBase} at runtime.
//
// webBase  = WebView <web-view src="..."> URL (the SPA host)
// apiBase  = wx.request URL prefix (the API host)
//
// Production nginx serves SPA at app.* and API at api.* — they are different
// subdomains. Today's miniapp conflates them via a bare-domain fallback;
// this resolver makes the split explicit.
//
// 正式版 (envVersion === "release") returns the same prod URLs the miniapp
// currently uses for real users. No behavior change for production.
function resolveBases() {
  // Devtools preview on a developer laptop: respect explicit config.js.
  // LAN dev (e.g. 192.168.x.x:5173) uses Vite's /api proxy so SPA host and
  // API host are the same — single base is correct here.
  try {
    if (wx.getSystemInfoSync().platform === "devtools" && runtimeConfig.apiBase) {
      return { webBase: runtimeConfig.apiBase, apiBase: runtimeConfig.apiBase };
    }
  } catch (_) { /* fall through */ }

  try {
    const env = wx.getAccountInfoSync().miniProgram.envVersion;
    if (env === "release") {
      return {
        webBase: "https://app.doctoragentai.cn",
        apiBase: "https://api.doctoragentai.cn",
      };
    }
    // develop / trial — only WeChat-listed members can reach this slot.
    return {
      webBase: "https://app.stg.doctoragentai.cn",
      apiBase: "https://api.stg.doctoragentai.cn",
    };
  } catch (_) { /* very old WeChat — ultimate fallback */ }

  return {
    webBase: "https://app.doctoragentai.cn",
    apiBase: "https://api.doctoragentai.cn",
  };
}

const bases = resolveBases();

App({
  globalData: {
    webBase: bases.webBase,
    apiBase: bases.apiBase,
    accessToken: "",
    doctorId: "",
    doctorName: "",
  },

  onLaunch() {
    this.globalData.accessToken = wx.getStorageSync("token") || "";
    this.globalData.doctorId   = wx.getStorageSync("doctorId") || "";
    this.globalData.doctorName = wx.getStorageSync("doctorName") || "";

    const updateManager = wx.getUpdateManager();
    updateManager.onUpdateReady(() => {
      wx.showModal({
        title: '更新提示',
        content: '新版本已准备好，是否重启应用？',
        success: (res) => { if (res.confirm) updateManager.applyUpdate(); },
      });
    });
    updateManager.onUpdateFailed(() => {
      console.warn('miniapp update failed');
    });
  },
});
```

- [ ] **Step 2: Update `config.example.js`**

```js
module.exports = {
  // Local dev only. Used by app.js when WeChat reports platform === "devtools"
  // (the laptop preview). On a real phone, app.js ignores this and reads
  // wx.getAccountInfoSync().miniProgram.envVersion to pick:
  //   release → webBase=app.* + apiBase=api.*
  //   develop / trial → webBase=app.stg.* + apiBase=api.stg.*
  //
  // For LAN dev: a single Vite host serves both SPA and /api proxy, so we
  // use the same value for both webBase and apiBase.
  apiBase: "http://localhost:5173",

  subscribeTemplateId: "",
};
```

- [ ] **Step 3: Update WebView-src readers**

`pages/doctor/doctor.js:36` — change:
```js
const webBase = app.globalData.apiBase;
```
to:
```js
const webBase = app.globalData.webBase;
```

`pages/login/login.js:28` — change:
```js
const webBase = app.globalData.apiBase;
```
to:
```js
const webBase = app.globalData.webBase;
```

- [ ] **Step 4: Devtools smoke test**

Open the miniprogram in WeChat devtools (laptop). In any page's `onLoad`:
```js
console.log("webBase:", getApp().globalData.webBase);
console.log("apiBase:", getApp().globalData.apiBase);
```
Expected: both equal `runtimeConfig.apiBase` (the LAN URL).

- [ ] **Step 5: Commit**

```bash
git add frontend/miniprogram/app.js
git add frontend/miniprogram/config.example.js
git add frontend/miniprogram/pages/doctor/doctor.js
git add frontend/miniprogram/pages/login/login.js
git commit -m "feat(miniprogram): split webBase/apiBase, route by envVersion at runtime"
```

---

## Task 12: CI tag guards (split into two workflows)

**Why this is a must-fix (Codex finding #4):** the existing `miniprogram-release.yml` triggers on **any** `v*` tag, with no branch verification. A tag pushed from a feature branch ships that branch's bundle to 开发版 of the prod appid. We split into two explicit workflows, each gated to its expected branch.

**Files:**
- Modify: `.github/workflows/miniprogram-release.yml` (rename/clarify; gate to `main`)
- Create: `.github/workflows/miniprogram-staging.yml` (gate to `staging`)

**Note on GitHub Actions tag matching:** GHA `on.push.tags` is **glob-style, not regex**. Patterns like `v[0-9]+.[0-9]+.[0-9]+` do not work — `+` is literal in glob. We use the `v*` glob (broad), then filter inside a job-level `if:` and verify branch-of-tag in a step.

- [ ] **Step 1: Modify the prod workflow**

Replace `.github/workflows/miniprogram-release.yml`:

```yaml
name: WeChat Mini Program — PROD upload

# Triggers on every v* tag, but the job's `if:` skips staging/rc tags.
# Then the first step refuses to upload if the tagged commit is not on `main`.
on:
  push:
    tags:
      - 'v*'

jobs:
  upload-miniprogram:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    # Skip staging/rc tags. Empty result = job is skipped (not failed).
    if: ${{ !contains(github.ref_name, '-staging-') && !contains(github.ref_name, '-rc-') }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # need full history for branch-contains check

      - name: Verify tag matches semver pattern
        run: |
          # Belt-and-suspenders: shell regex check the tag name.
          if ! [[ "$GITHUB_REF_NAME" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9._-]+)?$ ]]; then
            echo "::error::Tag ${GITHUB_REF_NAME} does not match v<semver>[-suffix]."
            exit 1
          fi

      - name: Verify tag is on main
        run: |
          if ! git branch -r --contains "$GITHUB_SHA" | grep -qE 'origin/main$'; then
            echo "::error::Tag ${GITHUB_REF_NAME} (commit ${GITHUB_SHA}) is not on origin/main."
            echo "Tag a commit that's been merged to main, or use a -staging- tag for staging."
            exit 1
          fi

      - uses: actions/setup-node@v4
        with: { node-version: '20' }

      - name: Build web frontend
        working-directory: frontend/web
        run: |
          npm ci
          VITE_API_BASE_URL=https://api.doctoragentai.cn npm run build

      - name: Install miniprogram-ci
        run: npm install -g miniprogram-ci

      - name: Write upload key
        run: echo "${{ secrets.MINIPROGRAM_UPLOAD_KEY }}" > /tmp/mp-upload-key.key

      - name: Extract version
        id: version
        run: echo "version=$(echo ${{ github.ref_name }} | sed 's/^v//' | sed 's/-.*//')" >> "$GITHUB_OUTPUT"

      - name: Build description
        id: desc
        run: |
          TAG_NAME="${{ github.ref_name }}"
          TAG_MSG=$(git tag -l --format='%(contents:subject)' "$TAG_NAME" 2>/dev/null || echo "")
          DESC="${TAG_NAME}${TAG_MSG:+ — $TAG_MSG}"
          echo "desc=${DESC:0:200}" >> "$GITHUB_OUTPUT"

      - name: Upload miniprogram (PROD path = app.stg.* branches won't ship here, this is the prod build)
        working-directory: frontend/miniprogram
        run: |
          miniprogram-ci upload \
            --pp ./ \
            --pkp /tmp/mp-upload-key.key \
            --appid wx9667f8091b342fb7 \
            --uv "${{ steps.version.outputs.version }}" \
            --desc "[PROD] ${{ steps.desc.outputs.desc }}" \
            -r 1 \
            --enable-es6 true \
            --enable-es7 true \
            --enable-minify true

      - name: Cleanup key
        if: always()
        run: rm -f /tmp/mp-upload-key.key
```

- [ ] **Step 2: Create the staging workflow**

`.github/workflows/miniprogram-staging.yml`:

```yaml
name: WeChat Mini Program — STAGING upload

# Glob `v*-staging-*` works as written: `*` is a valid glob wildcard.
# Refuses to upload if the tagged commit is not on `staging`.
# Lands in 开发版 of the same appid; resolveBases() at runtime sends it to the
# staging stack via wx.getAccountInfoSync().miniProgram.envVersion === "develop".
on:
  push:
    tags:
      - 'v*-staging-*'

jobs:
  upload-miniprogram-staging:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Verify tag matches v<semver>-staging-<date> pattern
        run: |
          if ! [[ "$GITHUB_REF_NAME" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-staging-[0-9A-Za-z._-]+$ ]]; then
            echo "::error::Tag ${GITHUB_REF_NAME} doesn't match v<semver>-staging-<id>."
            exit 1
          fi

      - name: Verify tag is on staging
        run: |
          if ! git branch -r --contains "$GITHUB_SHA" | grep -qE 'origin/staging$'; then
            echo "::error::Tag ${GITHUB_REF_NAME} (commit ${GITHUB_SHA}) is not on origin/staging."
            exit 1
          fi

      - uses: actions/setup-node@v4
        with: { node-version: '20' }

      - name: Build web frontend (staging)
        working-directory: frontend/web
        run: |
          npm ci
          VITE_API_BASE_URL=https://api.stg.doctoragentai.cn npm run build

      - name: Install miniprogram-ci
        run: npm install -g miniprogram-ci

      - name: Write upload key
        run: echo "${{ secrets.MINIPROGRAM_UPLOAD_KEY }}" > /tmp/mp-upload-key.key

      - name: Extract version
        id: version
        run: echo "version=$(echo ${{ github.ref_name }} | sed 's/^v//' | sed 's/-.*//')" >> "$GITHUB_OUTPUT"

      - name: Upload miniprogram
        working-directory: frontend/miniprogram
        run: |
          miniprogram-ci upload \
            --pp ./ \
            --pkp /tmp/mp-upload-key.key \
            --appid wx9667f8091b342fb7 \
            --uv "${{ steps.version.outputs.version }}" \
            --desc "[STAGING] ${{ github.ref_name }}" \
            -r 1 \
            --enable-es6 true \
            --enable-es7 true \
            --enable-minify true

      - name: Cleanup key
        if: always()
        run: rm -f /tmp/mp-upload-key.key
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/miniprogram-release.yml
git add .github/workflows/miniprogram-staging.yml
git commit -m "feat(ci): split miniprogram upload by env, gate by branch-of-tag"
```

---

## Task 13: Wire gitee staging webhook

**Type:** Manual ops (gitee + CVM)

- [ ] **Step 1: Confirm webhook server has staging config**

The webhook unit reads two env vars: `DEPLOY_SCRIPT_MAIN` and `DEPLOY_SCRIPT_STAGING`. Update the env file:
```bash
ssh ubuntu@CVM
sudo cat /etc/systemd/system/doctor-ai-webhook.service.d/override.conf 2>/dev/null \
  || sudo cat /etc/default/doctor-ai-webhook 2>/dev/null \
  || cat ~/.webhook.env  # whichever pattern your unit uses
```

Add (or confirm present):
```
DEPLOY_SCRIPT_MAIN=/home/ubuntu/deploy.sh
DEPLOY_SCRIPT_STAGING=/home/ubuntu/deploy-staging.sh
```

- [ ] **Step 2: Restart webhook**

```bash
sudo systemctl restart doctor-ai-webhook
sudo journalctl -u doctor-ai-webhook -n 20
```
Expected: log says `branches: main, staging`.

- [ ] **Step 3: Add gitee webhook (already exists for main)**

Gitee webhook config sends ALL branch pushes to the same endpoint. The dispatcher inside `webhook_server.py` (Task 3) decides what to do per ref. So **no second webhook URL is needed** — the existing `/hooks/deploy` already receives staging pushes once `staging` branch exists.

If your existing gitee webhook is filtered to push events on a specific branch, broaden it to all branches (the dispatcher will ignore unknown ones).

- [ ] **Step 4: Smoke test**

From laptop:
```bash
git checkout staging
git commit --allow-empty -m "chore(staging): webhook smoke test"
git push gitee staging
git checkout main
```

On CVM:
```bash
sudo journalctl -u doctor-ai-webhook -f
```
Expected within ~5s: `push event ref='refs/heads/staging' (branch='staging') ... starting staging deploy`. Then watch:
```bash
tail -f /home/ubuntu/doctor-ai-staging/logs/deploy.log
```
Expected: deploy completes in ~2-4 min.

---

## Task 14: First miniapp 开发版 upload

**Type:** Manual ops + CI

- [ ] **Step 1: Tag staging build**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
git checkout staging
git tag v1.3.0-staging-2026-04-27 -m "first staging upload"
git push gitee staging
git push github v1.3.0-staging-2026-04-27
```

- [ ] **Step 2: Watch the staging workflow**

GitHub Actions → `WeChat Mini Program — STAGING upload`. Expected: branch-on-staging guard passes, build runs, upload succeeds.

- [ ] **Step 3: Open 开发版 on phone**

WeChat 后台 → 版本管理 → 开发版 → find the upload → 体验版二维码. Open on a phone whose WeChat account is listed in WeChat 后台 → 成员管理 → 体验成员.

Expected:
- Miniapp loads.
- WebView src is `https://app.stg.doctoragentai.cn`.
- API requests in vConsole show `https://api.stg.doctoragentai.cn/api/...`.
- Login succeeds against staging (use WELCOME invite code from Task 5 step 4).

- [ ] **Step 4: Confirm 正式版 unaffected**

Open the public miniapp icon on any phone. Expected: hits `https://app.doctoragentai.cn` and `https://api.doctoragentai.cn` exactly as before.

---

## Task 15: Runbook

**Files:** `docs/deploy/staging.md` (per AGENTS.md docs table — `docs/deploy/` is the canonical home for deployment & infrastructure guides; `docs/operations/` is non-canonical).

- [ ] **Step 1: Write the runbook**

```markdown
# Staging Environment Runbook

## What it is

Cheap pre-prod on the same CVM as prod. Reaches `app.stg.doctoragentai.cn`
+ `api.stg.doctoragentai.cn`. Backend on `:8001`, MySQL schema
`doctor_ai_staging`, working tree `/home/ubuntu/doctor-ai-staging/`.
Auto-deploys on push to `gitee/staging`.

WeChat appid `wx9667f8091b342fb7`. 开发版 routes to staging; 正式版 routes to
prod (unchanged). Only WeChat-listed 开发者/体验者 can scan 开发版 QR.

## Add a tester

WeChat 后台 → 成员管理 → 体验成员 → 添加成员 → paste WeChat ID.

## Deploy to staging server

Just push:

    git checkout staging
    # ... edits ...
    git push gitee staging

Webhook → `deploy-staging.sh` (under `staging-build.slice` cgroup, so it
can't starve prod). ~2-4 min total.

## Deploy to staging miniapp slot

After a server-side staging deploy, upload the WebView shell:

    git checkout staging
    git tag v1.x.y-staging-YYYY-MM-DD -m "<reason>"
    git push github v1.x.y-staging-YYYY-MM-DD

GitHub Actions → `miniprogram-staging.yml` (gated to staging branch). On phone,
open 开发版 from WeChat 后台 → 版本管理.

## Promote staging build to 正式版

Confirmed working in 开发版? Two equally valid paths:

A) **Re-tag the same commit on `main`** (cleanest):
   1. Merge `staging` to `main`.
   2. Tag `vX.Y.Z` on main.
   3. Push tag → `miniprogram-release.yml` uploads.
   4. WeChat 后台 → 版本管理 → 提交审核 → 发布 (~24h audit).

B) **Submit the existing 开发版 directly**: WeChat 后台 → 开发版 → find the
   `[STAGING]` build → 提交审核. Same .wxapkg goes to 正式版; runtime envVersion
   flips from `develop` to `release` so the bundle now points at prod URLs.
   Caveat: the build was tested against staging URLs only.

(A) is safer; (B) is faster. Default to A.

## Reset staging DB

Reproducible. Uses `systemd-run --property=EnvironmentFile=` so the DSN never
appears in `ps`/`/proc/<pid>/cmdline`.

    ssh ubuntu@CVM
    mysql -u root -p -e "DROP DATABASE doctor_ai_staging; CREATE DATABASE doctor_ai_staging CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    sudo systemd-run --pty --quiet --collect --uid=ubuntu \
      --working-directory=/home/ubuntu/doctor-ai-staging \
      --property=EnvironmentFile=/etc/doctor-ai-staging.env \
      /home/ubuntu/doctor-ai-staging/.venv/bin/alembic upgrade head
    sudo systemd-run --pty --quiet --collect --uid=ubuntu \
      --working-directory=/home/ubuntu/doctor-ai-staging \
      --property=EnvironmentFile=/etc/doctor-ai-staging.env \
      /home/ubuntu/doctor-ai-staging/.venv/bin/python scripts/ensure_welcome_code.py

## Tail logs

    ssh ubuntu@CVM
    tail -f /home/ubuntu/doctor-ai-staging/logs/{backend,deploy}.log
    sudo journalctl -u doctor-ai-webhook -f

## Health checks

    curl https://api.stg.doctoragentai.cn/healthz
    curl -I https://app.stg.doctoragentai.cn/
    curl -s https://app.stg.doctoragentai.cn/wxABCDEF1234.txt   # WX-verify

## Resource caps

- Running staging service: `MemoryMax=2G`, `CPUQuota=150%` (in unit file).
- Staging deploy workload: `MemoryMax=4G`, `CPUQuota=200%`, `MemorySwapMax=0`
  (in `staging-build.slice`).

If staging starts misbehaving, check `systemctl status doctor-ai-staging` and
`systemd-cgls staging-build.slice`.

## Why same-CVM is "pre-prod" not "isolated staging"

Prod and staging share kernel, disk, MySQL instance, network, and (briefly)
deploy I/O. The cgroup caps minimize but don't eliminate this. For a true
isolation guarantee, move staging to a dedicated CVM.
```

- [ ] **Step 2: Commit**

```bash
git add docs/deploy/staging.md
git commit -m "docs(deploy): staging environment runbook"
```

---

## Task 16: Final verification

- [ ] **Step 1: Smoke test the full server-side loop**

1. Edit a visible string on `staging` branch, push.
2. Webhook log: `starting staging deploy` within 5s.
3. Deploy log: finishes in ~2-4 min.
4. `https://app.stg.doctoragentai.cn` reflects the change.
5. `https://app.doctoragentai.cn` does NOT.

- [ ] **Step 2: Smoke test the full miniapp loop**

1. Tag `v1.x.y-staging-DATE` on staging, push to GitHub.
2. CI guard accepts (commit is on staging).
3. Upload to 开发版 succeeds.
4. Phone with tester WeChat opens 开发版: WebView is `app.stg.*`, API is `api.stg.*`.
5. Phone with non-tester WeChat opens public icon: WebView is `app.*`, API is `api.*`. Identical to today.

- [ ] **Step 3: Verify CI guard rejects misuse**

Tag a `staging`-branch commit with a prod-style tag:
```bash
git checkout staging
git tag v9.9.9-rejection-test
git push github v9.9.9-rejection-test
```
Expected: `miniprogram-release.yml` runs, **fails** at `Verify tag is on main`. No upload.

Then delete the tag:
```bash
git tag -d v9.9.9-rejection-test
git push github :v9.9.9-rejection-test
```

- [ ] **Step 4: Verify per-branch lock works**

Push to both branches at once:
```bash
git checkout main && git commit --allow-empty -m "race-test prod" && git push gitee main &
git checkout staging && git commit --allow-empty -m "race-test staging" && git push gitee staging &
wait
```
Expected (in webhook log): both deploys start within seconds of each other; **neither is skipped**. Each holds its own branch lock.

- [ ] **Step 5: Verify deploy-time cgroup caps**

During a staging deploy, on the CVM:
```bash
systemd-cgtop -d 1 --order=memory | head
systemctl status staging-build.slice
```
Expected: the deploy-staging-* unit appears under `staging-build.slice` and respects `MemoryMax=4G`.

---

## Rollback

Same-CVM means rollback is fast. From most surgical to most aggressive:

1. **Revert miniapp change only** (if WeChat shipped a bad bundle):
   - Re-tag a known-good prod commit on `main`, push tag, WeChat audit, replace 正式版.
2. **Stop accepting staging traffic**:
   ```bash
   sudo systemctl stop doctor-ai-staging
   sudo rm /etc/nginx/sites-enabled/staging-{api,app}.doctoragentai.cn.conf
   sudo systemctl reload nginx
   ```
3. **Disable the webhook staging branch** (revert Task 3 to single-script behavior):
   ```bash
   sudo systemctl stop doctor-ai-webhook
   # Edit webhook_server.py back to the single-DEPLOY_SCRIPT version, restart.
   ```
4. **Drop schema** (last resort, no impact on prod):
   ```bash
   mysql -u root -p -e "DROP DATABASE doctor_ai_staging;"
   ```

The miniapp revert is the only step that touches the user-facing build. Everything else is server-side and invisible to public users.

---

## Open questions / known limitations

- **Same MySQL instance:** if prod has an InnoDB buffer-pool sizing problem, a heavy staging migration can degrade prod query latency. Acceptable for current traffic; revisit if real users complain.
- **Operator error with the wrong DSN:** mitigated by the env file's 0600 perms and the unit's `EnvironmentFile=` (not inline `Environment=`). Not eliminated. If you're hand-running scripts on the CVM, double-check `$DATABASE_URL` before running migrations.
- **Cold-cache `npm ci`:** ~3 min on first run after a tree wipe. Subsequent runs are <30s thanks to npm cache.
- **WeChat domain whitelist** is the security gate, not the runtime branch. If WeChat ever changes the gating model (e.g. lets non-listed users into 开发版), the runtime branch is no longer a security boundary, just a routing one. Audit annually.

## Out of scope (flagged for follow-up)

- **Prod `deploy/tencent/deploy.sh` ordering:** the staging deploy uses build-first ordering (Task 9). The prod deploy still uses migrate-before-build. Same mixed-state failure mode applies (npm OOM after alembic ran → service runs old code on new schema). Touching prod's deploy is out of scope for this plan because the user explicitly wants prod behavior unchanged. **Recommended follow-up:** open a separate PR that flips ordering in `deploy/tencent/deploy.sh` to match staging, after staging has soaked for ≥1 week.
