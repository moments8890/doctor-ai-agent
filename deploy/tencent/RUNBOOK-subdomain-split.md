# Subdomain split runbook

Take `api.doctoragentai.cn` from "everything-on-one-host" to four scoped
hosts. Designed for zero downtime — old paths keep redirecting for a
release after cutover. **All risky steps run on the Tencent host as root**;
the repo holds the configs and scripts that get deployed there via
gitee → `deploy.sh`.

## Target

| Host | Purpose | Auth |
|---|---|---|
| `api.doctoragentai.cn` | JSON API only | public, JWT |
| `app.doctoragentai.cn` | Doctor + patient SPA | public |
| `wiki.doctoragentai.cn` | Public docs | public (gate 内部 later) |
| `ops.doctoragentai.cn` | glitchtip + dbgate | basic-auth + IP allowlist |

One wildcard cert `*.doctoragentai.cn` covers all four.

---

## What needs human input before you start

| Item | Why | Where it goes |
|---|---|---|
| Home + office IPv4(s) | `allow` directives | `nginx/ops.doctoragentai.cn.conf` and `nginx/phase0-lockdown.conf` |
| Basic-auth username + password | gates internal tools | `htpasswd -c /etc/nginx/htpasswd <user>` |
| DNSPod API id + key | wildcard cert renewal | `DP_Id` / `DP_Key` env at first cert issuance |
| WeChat console access | request domain allowlist | minprogram dashboard |

---

## Phase 0 — emergency lockdown (10 min, do today)

Closes the open hole on `/glitchtip/`, `/dbgate/` while the rest
of the migration is rolled out. Zero infra change.

```bash
ssh ubuntu@<tencent-host>
sudo apt install -y apache2-utils  # provides htpasswd
sudo htpasswd -c /etc/nginx/htpasswd opsuser  # set a password

# Edit deploy/tencent/nginx/phase0-lockdown.conf — replace
# YOUR.HOME.IP / YOUR.OFFICE.IP placeholders. Commit, push to gitee,
# and let the webhook deploy.sh sync the file. THEN paste its contents
# into the existing api.doctoragentai.cn 443 server block, BEFORE the
# catch-all `location /`. (Your existing nginx config lives at
# /etc/nginx/sites-enabled/<something> — find it with `nginx -T`.)

sudo nginx -t && sudo systemctl reload nginx

# Verify
curl -sI https://api.doctoragentai.cn/glitchtip/   # expect 401
curl -u opsuser:<pw> -sI https://api.doctoragentai.cn/glitchtip/  # expect 200/302 from the IP allowlist range
```

If you can't or won't do basic-auth, at minimum add the `allow / deny`
directives — IP-only is weaker but better than open.

---

## Phase 1 — wildcard SSL cert (1 hr)

```bash
ssh ubuntu@<tencent-host>

# Install acme.sh (one-time)
curl https://get.acme.sh | sh -s email=you@doctoragentai.cn
source ~/.bashrc  # picks up acme.sh alias

# Tencent DNSPod token: https://console.dnspod.cn/account/token/apikey
export DP_Id=<id>
export DP_Key=<token>

# Provision the cert. Stored in ~/.acme.sh/, installed into
# /etc/nginx/certs/wildcard.doctoragentai.cn.{crt,key}.
sudo -E /home/ubuntu/doctor-ai-agent/deploy/tencent/scripts/issue-wildcard-cert.sh

# Confirm
sudo openssl x509 -in /etc/nginx/certs/wildcard.doctoragentai.cn.crt -noout -dates -subject
crontab -l | grep acme.sh   # daily renewal cron should be present
```

If DNS-01 fails: check that the CNAME `_acme-challenge.doctoragentai.cn`
isn't shadowed by another record at DNSPod, and that the API token has
record-modify scope.

---

## Phase 2 — DNS records (5 min, propagation ≤ 10 min)

At Tencent DNSPod, add three A records pointing at the same host as
`api.doctoragentai.cn`:

| Name | Type | Value |
|---|---|---|
| `app` | A | `<tencent-host-ip>` |
| `wiki` | A | `<tencent-host-ip>` |
| `ops` | A | `<tencent-host-ip>` |

Verify before continuing:

```bash
dig +short app.doctoragentai.cn
dig +short wiki.doctoragentai.cn
dig +short ops.doctoragentai.cn
```

(Apex `doctoragentai.cn` and `api.*` stay as they are.)

---

## Phase 3 — provision new vhosts (15 min)

```bash
ssh ubuntu@<tencent-host>
cd /home/ubuntu/doctor-ai-agent

# Make sure the latest configs are on the host (deploy.sh runs git
# reset --hard gitee/main, so any commit on gitee will sync them).
git fetch gitee && git reset --hard gitee/main

# Edit ops.doctoragentai.cn.conf to replace YOUR.HOME.IP / YOUR.OFFICE.IP.
# Either edit in repo + redeploy, or sed-replace in place:
sudo sed -i \
  -e 's/YOUR.HOME.IP/1.2.3.4/' \
  -e 's/YOUR.OFFICE.IP/5.6.7.8/' \
  deploy/tencent/nginx/ops.doctoragentai.cn.conf

sudo /home/ubuntu/doctor-ai-agent/deploy/tencent/scripts/install-vhosts.sh
```

Verify each host:

```bash
curl -sI https://api.doctoragentai.cn/healthz  # 200
curl -sI https://app.doctoragentai.cn/         # 200
curl -sI https://wiki.doctoragentai.cn/        # 200
curl -sI https://ops.doctoragentai.cn/         # 401 — auth required
curl -u opsuser:<pw> -sI https://ops.doctoragentai.cn/glitchtip/  # 302 to login
```

The OLD `api.doctoragentai.cn` server block still serves the SPA and
the legacy paths at this point — both old and new URLs work.

---

## Phase 4 — frontend + WeChat allowlist (30 min)

### Backend CORS

`CORS_ALLOW_ORIGINS` must list the new origin. The systemd unit at
`deploy/tencent/doctor-ai-backend.service` doesn't set this; it lives
in your runtime config (likely `runtime.json` or a `.env` next to it).
Add `https://app.doctoragentai.cn` (and any others you call from):

```
CORS_ALLOW_ORIGINS=https://app.doctoragentai.cn,https://api.doctoragentai.cn,https://wiki.doctoragentai.cn,<wechat-miniprogram-origin-if-any>
```

Then `sudo systemctl restart doctor-ai-backend`.

### Frontend build

`frontend/web/.env.android` already pins
`VITE_API_BASE_URL=https://api.doctoragentai.cn` — no change needed for
the WeChat miniapp build. For the web SPA build, the in-repo build
emits same-origin URLs (`""` base) so the browser hits whatever host
served the page. Once the SPA moves to `app.*`, that means cross-origin
to `api.*` — works because of the CORS update above.

If you want the SPA to use absolute API URLs:

```bash
# Add to frontend/web/.env.production
VITE_API_BASE_URL=https://api.doctoragentai.cn
```

### WeChat miniprogram allowlist

In the WeChat miniprogram admin
(<https://mp.weixin.qq.com/> → 开发 → 开发管理 → 开发设置 → 服务器域名),
add to **request合法域名**:

- `https://app.doctoragentai.cn`
- `https://api.doctoragentai.cn`
- `https://wiki.doctoragentai.cn`

Tencent caches this list aggressively. Add the entries **before** any
production miniapp release that would call the new hosts.

---

## Phase 5 — soft cutover (1 day soak, then drop)

For ~24h, `app.*`, `wiki.*`, `ops.*` and the legacy paths on `api.*` all
work. Use the new URLs daily; watch for issues (CORS errors, missing
assets, broken WeChat calls).

When you're ready to retire the legacy paths:

```bash
# The new api.doctoragentai.cn.conf already returns 301 redirects for
# /wiki/, /glitchtip/, /dbgate/. Replace the OLD api.* server
# block with the new one — install-vhosts.sh will have already done
# this if your previous block was at sites-enabled/api.doctoragentai.cn.conf.

# If the old block lives elsewhere (e.g. /etc/nginx/sites-enabled/default),
# remove or rename it so it doesn't shadow the new file:
sudo mv /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/default.disabled
sudo nginx -t && sudo systemctl reload nginx
```

After another week with no fallback hits in access logs, you can edit
`api.doctoragentai.cn.conf` and remove the four 301 redirects. They're
documented inline in that file as "drop after one release cycle".

---

## Phase 6 — deploy.sh (no change needed)

The build pipeline produces `frontend/dist/` (already does). Both
`app.*` (root → dist) and `wiki.*` (root → dist/wiki) read from there
on every deploy. No script change.

The ops tools (glitchtip, dbgate) keep their existing
docker-compose lifecycle — out of band from `deploy.sh`, untouched.

---

## Rollback

| Symptom | Action |
|---|---|
| New vhost serves wrong content | `sudo rm /etc/nginx/sites-enabled/<host>.conf && sudo systemctl reload nginx` — old `api.*` config still has the legacy paths intact, no functionality lost |
| WeChat miniapp can't reach `api.*` after cutover | Check WeChat console allowlist + redeploy miniapp build with old URLs as a stopgap |
| Cert renewal fails silently | `sudo openssl x509 -in /etc/nginx/certs/wildcard.doctoragentai.cn.crt -noout -enddate` — if < 14d, re-run `issue-wildcard-cert.sh` |
| CORS error from `app.*` to `api.*` | Verify `CORS_ALLOW_ORIGINS` in runtime config includes `https://app.doctoragentai.cn`, restart backend |

---

## File map

```
deploy/tencent/
├── nginx/
│   ├── phase0-lockdown.conf         # interim guard for current api.* (Phase 0)
│   ├── api.doctoragentai.cn.conf    # final api-only vhost (Phase 3)
│   ├── app.doctoragentai.cn.conf    # SPA host (Phase 3)
│   ├── wiki.doctoragentai.cn.conf   # docs host (Phase 3)
│   └── ops.doctoragentai.cn.conf    # gated tools host (Phase 3)
├── scripts/
│   ├── issue-wildcard-cert.sh       # acme.sh wildcard, idempotent (Phase 1)
│   └── install-vhosts.sh            # symlinks vhosts + reloads nginx (Phase 3)
└── RUNBOOK-subdomain-split.md       # this file
```
