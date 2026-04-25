# Production services map — Tencent CVM

Reference doc for what runs where, who owns what, and where to look when
something breaks. Companion to:

- [`RUNBOOK-subdomain-split.md`](./RUNBOOK-subdomain-split.md) — how the
  current host/cert/CORS setup was built
- [`deploy.sh`](./deploy.sh) — what runs on every gitee push
- [`adminer.md`](./adminer.md), [`glitchtip.md`](./glitchtip.md) —
  per-tool first-time setup

---

## Host

| Item | Value |
|---|---|
| Provider | Tencent Cloud CVM |
| Region | `ap-shanghai` |
| Instance ID | `ins-ijnd8p4d` |
| Instance name | `doctor-ai-prod-cvm-01` |
| Public IP | `101.35.116.122` |
| OS | Ubuntu (nginx 1.18, Python 3.10) |
| App root | `/home/ubuntu/doctor-ai-agent` |
| Deploy trigger | Gitee webhook on push → `/home/ubuntu/deploy.sh` (symlink to `deploy/tencent/deploy.sh`) |
| Remote ops | TAT agent (`tccli tat RunCommand`) — no SSH key required for the operator account |

---

## Subdomains

All four point at `101.35.116.122`. SSL is one multi-SAN Let's Encrypt
cert (`/etc/letsencrypt/live/api.doctoragentai.cn/`) — certbot auto-renews.

| Host | Vhost file | Public? | Auth | Backed by |
|---|---|---|---|---|
| `api.doctoragentai.cn` | `/etc/nginx/sites-enabled/doctoragentai.cn` | Yes | JWT (FastAPI middleware) | uvicorn `:8000` — JSON API only after Phase 5 cutover; `/api/admin/*` permanently 301s to `admin.*` |
| `app.doctoragentai.cn` | `/etc/nginx/sites-enabled/app.doctoragentai.cn` | Yes | JWT only | Static `/home/ubuntu/doctor-ai-agent/frontend/dist` (the SPA) |
| `wiki.doctoragentai.cn` | `/etc/nginx/sites-enabled/wiki.doctoragentai.cn` | Yes | None (public docs only — 内部 sidebar removed) | Static `frontend/dist/wiki` |
| `ops.doctoragentai.cn` | `/etc/nginx/sites-enabled/ops.doctoragentai.cn` | **No** | basic-auth + IP allowlist `50.47.192.0/20` (`satisfy all`) | Internal tools (see below) |
| `admin.doctoragentai.cn` | `/etc/nginx/sites-enabled/admin.doctoragentai.cn` | **No** | basic-auth (vhost-level) + app-layer `X-Admin-Token` (`require_admin_role`) | SPA (same `frontend/dist` as app.*) + `/api/*` proxy to `:8000`; admin SPA mounts at `/admin/login` and `/admin/*` |

DNS records live at DNSPod (Tencent) — managed via
`tccli dnspod {Describe,Create,Modify}Record` on the
`claude-automation` CAM user. Domain ID: `98987909`.

---

## API surface — `api.doctoragentai.cn`

The doctor-ai-agent FastAPI app on `127.0.0.1:8000`. nginx
`location` blocks:

| Path | Forwards to | Notes |
|---|---|---|
| `/api/*` | `127.0.0.1:8000` | All authenticated REST endpoints. CORS configured to allow `https://api.*`, `https://app.*`, `https://wiki.*`, `https://localhost`, `http://localhost`. |
| `/healthz` | nginx-direct `200 ok` | Liveness probe — bypasses backend |
| `/wechat` | `127.0.0.1:8000` | WeChat callback (token verification + miniprogram messages) |
| `/ws/*` | `127.0.0.1:8000` | WebSocket upgrade (live updates) |
| `/download/*` | `127.0.0.1:8000` | Signed download URLs (PDF exports etc.) |
| `/test/*` | `127.0.0.1:8000` | Internal smoke endpoints (debug; `UI_DEBUG_TOKEN` gate) |
| `/hooks/deploy` | `127.0.0.1:9000` | Gitee webhook receiver (separate `webhook_server.py`) |
| `/.well-known/acme-challenge/` | `/var/www/certbot` | certbot HTTP-01 challenge serving |
| `/wiki/`, `/glitchtip/`, `/dbgate/` | 301 redirect | Legacy paths → wiki.* / ops.* — drop after one release cycle |
| `/` (and `/login`, `/doctor/*`, `/patient/*`, `/admin/*`) | 301 → `https://app.doctoragentai.cn$request_uri` | Catch-all — bookmarks against the old everything-on-api.* URL survive cutover by redirecting to the new SPA host |

### Auth model (`api.*`)

- **Public endpoints**: `/healthz`, `/api/auth/unified/*` (login/register), `/api/auth/unified/doctors` (doctor list for patient sign-up), `.well-known/*`
- **JWT-protected**: most `/api/**` — `Authorization: Bearer <token>` from
  `unified_auth_token` localStorage key. Token is HS256-signed with the
  shared secret in `runtime.json:JWT_SECRET`.
- **Role enforcement**: `require_doctor()` / `require_patient()` deps in
  `infra/auth/unified.py`.

### CORS (`/api/**`)

Configured via `runtime.json:CORS_ALLOW_ORIGINS` — comma-separated:

```
https://api.doctoragentai.cn
https://app.doctoragentai.cn
https://wiki.doctoragentai.cn
https://localhost
http://localhost
```

Allows credentials. Methods: `GET POST PUT PATCH DELETE OPTIONS`.
Headers: `Authorization Content-Type X-Admin-Token X-Trace-Id` (+
standards). Edit at `config/runtime.json` →
`categories.<cat>.settings.CORS_ALLOW_ORIGINS.value`, then
`systemctl restart doctor-ai-backend`.

---

## Internal tools — `ops.doctoragentai.cn`

Each is its own docker container; nginx proxies subpaths into them. All
gated by **basic-auth + IP allowlist** at the vhost level (`satisfy all`).

| Path | Upstream | Tool | Setup doc |
|---|---|---|---|
| `/glitchtip/` | `127.0.0.1:8100` | GlitchTip — Sentry-compatible error tracking | [glitchtip.md](./glitchtip.md) |
| `/glitchtip/api/` | `127.0.0.1:8100/api/` | **Carve-out** — `auth_basic off; allow all`. Sentry SDK ingest path; auth happens at GlitchTip layer via DSN key in `X-Sentry-Auth` | (carve-out: `ops.doctoragentai.cn.conf:55-69`) |
| `/dbgate/` | `127.0.0.1:8101` | dbgate — DB UI | [adminer.md](./adminer.md) (file is named "adminer" but the tool is dbgate) |

### Auth

- **htpasswd**: `/etc/nginx/.dbgate-htpasswd` — single shared file across
  all internal-tool paths. Rotate with
  `htpasswd /etc/nginx/.dbgate-htpasswd <user>` then `nginx -s reload`.
- **IP allowlist**: `50.47.192.0/20` (Comcast WA residential block).
  Edit `/etc/nginx/sites-enabled/ops.doctoragentai.cn` → the `allow`
  directive in the server block, then `nginx -s reload`. To open up
  for a different location, add another `allow X.Y.Z.0/24;` line above
  the `deny all`.

### Connecting from outside the allowlist

If you're traveling and your IP isn't in the `/20`, you have three
options:

1. SSH-tunnel through the Tencent host:
   `ssh -L 8100:127.0.0.1:8100 ubuntu@101.35.116.122` then visit
   `http://localhost:8100/`.
2. Add a temporary `allow <new_ip>;` to the ops vhost and reload nginx
   (revert when done).
3. VPN to a network already in `50.47.192.0/20`.

---

## Backend service

| Item | Value |
|---|---|
| Unit | `doctor-ai-backend.service` |
| Source unit | `deploy/tencent/doctor-ai-backend.service` (in repo) |
| Active unit | `/etc/systemd/system/doctor-ai-backend.service` |
| Drop-ins | `/etc/systemd/system/doctor-ai-backend.service.d/{release,sentry}.conf` |
| ExecStart | `cli.py start --prod --no-frontend --host 0.0.0.0 --port 8000` |
| Logs | `/home/ubuntu/doctor-ai-agent/logs/backend.log` + journalctl |
| Restart | `sudo systemctl restart doctor-ai-backend` |
| Health | `curl https://api.doctoragentai.cn/healthz` |

### Configuration sources (read order)

1. `os.environ` (set by systemd unit + drop-ins)
2. `config/runtime.json` (loaded in `src/main.py:23`, merges into env if not present)
3. Code defaults

The unit drop-ins inject `GIT_COMMIT` (set by `deploy.sh` after each
git pull, used as Sentry release tag) and `SENTRY_DSN`. Everything
else (CORS, DB URL, LLM keys, WeChat secrets) lives in
`config/runtime.json` — never in the unit file.

### Sentry (`SENTRY_DSN`)

```
https://<key>@ops.doctoragentai.cn/glitchtip/1
```

Configured in `/etc/systemd/system/doctor-ai-backend.service.d/sentry.conf`.
SDK calls `/glitchtip/api/1/envelope/` — passes through the carve-out,
authenticates by DSN key at GlitchTip. Verify ingest is flowing:

```bash
tail -50 /var/log/nginx/access.log | grep "/glitchtip/api/" | tail
# Look for: POST /glitchtip/api/1/envelope/ → 200 from sentry.python/*
# 401 means basic-auth gate caught it (carve-out broken)
# 403 means IP gate caught it (carve-out broken)
```

---

## Database

| Item | Value |
|---|---|
| Engine | MySQL 8 (in docker-compose, alongside backend) |
| Connection | `mysql+aiomysql://doctor_ai:***@mysql:3306/doctor_ai?charset=utf8mb4` |
| Connection string source | `runtime.json:DATABASE_URL` (a.k.a. `runtime.prod.json` if `ENVIRONMENT=production`) |
| DDL | Alembic only — `ENVIRONMENT=production alembic upgrade head` (run by `deploy.sh`) |
| Web admin | dbgate at `https://ops.doctoragentai.cn/dbgate/` |
| Local backups | None scheduled (dev DB is SQLite at `/home/ubuntu/doctor-ai-agent/data/patients.db`) |

---

## Storage

| Item | Path / source |
|---|---|
| Static SPA bundle | `/home/ubuntu/doctor-ai-agent/frontend/dist/` (rebuilt on every deploy) |
| Wiki HTML | `frontend/dist/wiki/` (subdir of above) |
| User uploads (audio, photo) | `/home/ubuntu/doctor-ai-agent/uploads/` |
| Backed up to | Tencent COS — incremental sync via cron, see `auto_deploy_on_drift.sh` and recent commits `522fbc1c`, `b18e9354` |
| Logs | `/home/ubuntu/doctor-ai-agent/logs/` (rotated by logrotate; backend writes via systemd `StandardOutput=append`) |

---

## SSL

| Item | Value |
|---|---|
| Type | Multi-SAN Let's Encrypt (RSA 2048) |
| SANs | `api`, `app`, `wiki`, `ops` (all `.doctoragentai.cn`) |
| Cert | `/etc/letsencrypt/live/api.doctoragentai.cn/fullchain.pem` |
| Key | `/etc/letsencrypt/live/api.doctoragentai.cn/privkey.pem` |
| Issuer | certbot 1.21.0 (HTTP-01 via webroot `/var/www/certbot`) |
| Renewal | certbot's built-in cron timer; verify with `systemctl list-timers \| grep certbot` |
| Adding a new subdomain | Add A record at DNSPod, then `certbot certonly --webroot -w /var/www/certbot --expand --cert-name api.doctoragentai.cn -d api.doctoragentai.cn -d ... -d <new>.doctoragentai.cn` and reload nginx |

Future: migrate to wildcard via `acme.sh` + DNSPod plugin — script at
`deploy/tencent/scripts/issue-wildcard-cert.sh` is ready, just needs the
DNSPod credentials exported once. Wildcard avoids needing to re-issue
when adding subdomains.

---

## DNS records (`doctoragentai.cn` at DNSPod)

| Name | Type | Value | TTL |
|---|---|---|---|
| `@` | NS | `clark.dnspod.net.`, `optional.dnspod.net.` | 86400 |
| `@` | MX | `mxbiz1.qq.com.` | 600 |
| `@` | TXT | SPF: `v=spf1 include:qcloudmail.com ~all` | 600 |
| `qcloud._domainkey` | TXT | DKIM (Tencent SES) | 600 |
| `_dmarc` | TXT | `v=DMARC1; p=none` | 600 |
| `api` | A | `101.35.116.122` | 600 |
| `app` | A | `101.35.116.122` | 600 |
| `wiki` | A | `101.35.116.122` | 600 |
| `ops` | A | `101.35.116.122` | 600 |

Apex `doctoragentai.cn` has **no** A record yet — visiting the bare
domain returns NXDOMAIN. Add one if you want a marketing landing page.

CAA: see `3633c6bb` for the recently added CAA record (limits which
CAs can issue certs for the domain).

---

## Frontend integration

The doctor + patient SPA reads its API base from build-time env:

| Build target | `VITE_API_BASE_URL` | Source |
|---|---|---|
| Web (default) | `""` (same-origin) | falls back to whatever host served the page |
| WeChat miniapp | `https://api.doctoragentai.cn` | `frontend/web/.env.android` |
| E2E tests | `http://127.0.0.1:8001` | `tests/e2e/fixtures/doctor-auth.ts:20` (E2E_API_BASE_URL override) |

Now that `api.*` is JSON-only and the SPA lives at `app.*`, the web
build IS effectively cross-origin: the page loaded from `app.*` calls
`api.*` via `fetch()`, and CORS at the FastAPI layer (`runtime.json:
CORS_ALLOW_ORIGINS`) gates which origins are allowed. If you set
`VITE_API_BASE_URL=https://api.doctoragentai.cn` explicitly in the
production build, you make that boundary unmissable in the source —
worth doing at the next frontend build cycle to avoid surprise when
someone deploys the SPA to a third host and forgets the CORS config.

---

## Operational commands cheat-sheet

```bash
# Deploy a new commit (manual; usually webhook-driven)
ssh ubuntu@101.35.116.122
cd /home/ubuntu/doctor-ai-agent && bash deploy/tencent/deploy.sh

# Restart the backend
sudo systemctl restart doctor-ai-backend
sudo journalctl -u doctor-ai-backend -f

# Reload nginx after a config edit
sudo nginx -t && sudo systemctl reload nginx

# Tail the access log filtered to API requests
sudo tail -f /var/log/nginx/access.log | grep " /api/"

# Check Sentry ingest health (count 200s vs 401s in last 100 events)
sudo tail -200 /var/log/nginx/access.log | awk '$7 ~ "/glitchtip/api/" {print $9}' | sort | uniq -c

# Add an IP to the ops allowlist
sudo nano /etc/nginx/sites-enabled/ops.doctoragentai.cn  # add `allow X.Y.Z.0/24;` near the existing allow
sudo nginx -t && sudo systemctl reload nginx

# Rotate the ops basic-auth password
sudo htpasswd /etc/nginx/.dbgate-htpasswd opsuser
# (no nginx reload needed — htpasswd is read on every request)
```

---

## Pending / known follow-ups

- **Drop the legacy 301 redirects on `api.*`** — after ~1 release cycle
  with no fallback hits in the access log, remove the `/wiki/`,
  `/glitchtip/`, `/dbgate/`, and catch-all `/ → app.*` rules from
  `deploy/tencent/nginx/api.doctoragentai.cn.conf`. Until then they're
  load-bearing for any old bookmarks / shared links.
- **One-time re-login** — users who were logged in on the old
  `api.doctoragentai.cn` SPA have their JWT in `api.*` localStorage.
  When they next visit, the 301 to `app.*` lands them on a fresh origin
  with empty storage → forced to log in again once. No long-term issue;
  no action required unless complaints come in.
- **Wiki 内部 page files** — `wiki-specs.html` and
  `wiki-smoke-gallery.html` are no longer linked from the public wiki
  sidebar but the files still ship in `frontend/dist/wiki/` (reachable
  by direct URL). If the screenshots or specs are sensitive, move them
  to `ops.doctoragentai.cn/internal-wiki/` (auth-gated) and delete from
  `frontend/web/public/wiki/`.
- **Wildcard cert** — current cert is multi-SAN; adding a new subdomain
  needs `certbot --expand`. Migrate to wildcard via
  `scripts/issue-wildcard-cert.sh` to make new subdomains zero-touch
  for SSL.
- **IP allowlist drift** — `50.47.192.0/20` is Comcast WA residential.
  When you change ISPs / travel, the allowlist will lock you out;
  budget for this (or move to a VPN endpoint).
