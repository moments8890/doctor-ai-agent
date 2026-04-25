# Admin Subdomain Split — `admin.doctoragentai.cn` (post-soak)

> **Status:** PLANNED — execute AFTER the 2-3 day soak window started
> 2026-04-25. Not urgent: the auth bug fix in `d0bdeccc` already closes
> the actual leak. This plan is defense in depth.

## Why

After commit `9e512847` we have `api / app / wiki / ops` vhosts. `admin.*`
is the missing sibling. A dedicated vhost gives us:

- **nginx-level IP allowlist on the entire host** — 3 lines, no path
  matching, can't accidentally leak a new admin route by forgetting to
  add it to a whitelist
- **separate WAF / rate limit policy** — admin traffic profile is
  fundamentally different from public API traffic
- **clearer mental model** — `admin.*` is obviously restricted; bots
  scraping `api.*` for `/api/admin/*` get nothing
- **separate access logs** — admin requests in their own file, not
  buried in api.* traffic
- **easier post-incident forensics** — "did anyone hit admin from a
  weird IP?" becomes a one-grep question

Cost: ~half-day of work. Mostly nginx + frontend URL plumbing. No new
cert needed (wildcard already covers `admin.doctoragentai.cn`).

## Sequence (post-soak)

1. **This plan first** — admin vhost lands, IP allowlist applied.
2. THEN nginx IP allowlist refinement (broader hygiene; this plan unblocks it)
3. THEN wildcard cert posture review (mostly done — already in use)
4. THEN wiki 内部 scrub
5. THEN Phase 5 frontend cutover (already shipped as default, just removing the v1 fallback)

## Pre-flight check

Already in place — no setup needed:

- ✅ Wildcard cert at `/etc/nginx/certs/wildcard.doctoragentai.cn.crt`
- ✅ DNS for `*.doctoragentai.cn` routes to the same Tencent host
- ✅ `htpasswd` at `/etc/nginx/htpasswd` (used by ops.*)
- ✅ Auth-token logic at app layer (`require_admin_role`) is already in place
- ✅ Auth bug closed (commit `d0bdeccc` 2026-04-25)

To verify before starting:

```bash
# DNS resolves
dig +short admin.doctoragentai.cn   # should match api.* / ops.*

# Cert covers admin.*
openssl x509 -in /etc/nginx/certs/wildcard.doctoragentai.cn.crt -noout -text \
  | grep -A1 "Subject Alternative Name"
# expect: *.doctoragentai.cn or admin.doctoragentai.cn explicit
```

## The vhost

Mirror `ops.doctoragentai.cn.conf` — same gate pattern (basic auth +
IP allowlist + `satisfy all`), different upstream (FastAPI :8000 instead
of GlitchTip / DBGate). The app-layer X-Admin-Token check stays —
that's the third gate.

Save as `deploy/tencent/nginx/admin.doctoragentai.cn.conf`:

```nginx
# admin.doctoragentai.cn — operations console for the partner doctor + super.
#
# Three gates (defense in depth):
#   1. nginx IP allowlist (allow / deny / satisfy all at the vhost level)
#   2. nginx auth_basic (htpasswd at /etc/nginx/htpasswd, shared with ops.*)
#   3. app-layer X-Admin-Token (require_admin_role / require_admin_super)
#
# Mounts:
#   /              → SPA bundle (admin v3 served from app.* assets, see note)
#   /api/admin/    → FastAPI on :8000
#   /healthz       → nginx-served, NOT gated (deploy probes need this)

server {
    listen 80;
    listen [::]:80;
    server_name admin.doctoragentai.cn;
    location /.well-known/acme-challenge/ { root /var/www/certbot; try_files $uri =404; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name admin.doctoragentai.cn;

    ssl_certificate     /etc/nginx/certs/wildcard.doctoragentai.cn.crt;
    ssl_certificate_key /etc/nginx/certs/wildcard.doctoragentai.cn.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    client_max_body_size 20m;

    # ── Vhost-level gates: ALL three must pass ──────────────────────
    auth_basic "admin";
    auth_basic_user_file /etc/nginx/htpasswd;
    allow YOUR.HOME.IP;
    allow YOUR.OFFICE.IP;
    # Add 陈宇明's IP here when he's onsite at the partner hospital.
    # allow PARTNER.HOSPITAL.IP;
    deny all;
    satisfy all;

    # ── Healthz: NOT gated (deploy probes hit this) ─────────────────
    location = /healthz {
        auth_basic off;
        allow all;
        add_header Content-Type text/plain;
        return 200 'ok';
    }

    # ── certbot HTTP-01 (in case we ever rotate to per-host cert) ───
    location /.well-known/acme-challenge/ {
        auth_basic off;
        allow all;
        root /var/www/certbot;
        try_files $uri =404;
    }

    # ── /api/admin/* → FastAPI ──────────────────────────────────────
    location /api/admin/ {
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-Id $request_id;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
        proxy_send_timeout 120s;
        proxy_pass http://127.0.0.1:8000;
    }

    # ── SPA: serve the admin v3 bundle ──────────────────────────────
    # Option A (simpler): proxy / to app.* and let app.* serve the SPA
    # which then renders the admin route normally. CORS-free because
    # /api/admin/ is same-origin via this vhost.
    #
    # Option B: serve the SPA bundle directly from this host (separate
    # build artifact). Cleaner separation; requires a build step that
    # outputs an admin-only bundle. Defer to v2 of this migration.
    location / {
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://127.0.0.1:8000;  # SPA served via FastAPI's
                                            # static fallback, OR proxy
                                            # to app.* if SPA lives there.
    }
}
```

Pick option A (proxy to backend's static SPA fallback) for v1 — cleanest
to deploy. Option B can wait.

## App-layer changes — the path question

Two options for how the new admin URL works for the partner doctor:

**Option α (recommended): full SPA at admin.\***
- He visits `https://admin.doctoragentai.cn/?doctor=<id>`
- The SPA loads, calls `/api/admin/*` same-origin (no CORS).
- All existing JSX works unchanged because admin v3 already uses
  relative URLs (`fetch("/api/admin/overview")`).
- Only the nginx vhost is new; no frontend code changes.

**Option β: cross-origin to api.\***
- He visits `https://admin.doctoragentai.cn` which serves the SPA shell.
- SPA calls `https://api.doctoragentai.cn/api/admin/*` cross-origin.
- Requires CORS allowlist for `https://admin.doctoragentai.cn` in
  `runtime.json` `CORS_ALLOW_ORIGINS`.
- Cookie scope review needed (session cookies are domain-scoped).

**Pick α.** Same-origin is simpler and we already have the SPA shipped
through the FastAPI catch-all; just point the new vhost at port 8000
for `/` and admin v3 mounts cleanly.

## Block public api.* from serving admin (after admin.* is live)

After the new vhost is verified, gate `/api/admin/*` on `api.*` to
401 anyone who lands there from a stale URL:

In `deploy/tencent/nginx/api.doctoragentai.cn.conf`, before the `/api/`
block, add:

```nginx
location ~ ^/api/admin/ {
    return 301 https://admin.doctoragentai.cn$request_uri;
}
```

(Use 301 not 410 — the URL is moving, not gone. Existing automation hitting
`api.*/api/admin/*` survives the move; only the public endpoint changes.)

## Migration steps (in order)

1. **Add the IP allowlist values.** Edit
   `deploy/tencent/nginx/admin.doctoragentai.cn.conf` — replace
   `YOUR.HOME.IP` / `YOUR.OFFICE.IP` with real values. Confirm these
   IPs from `who | grep -E "^chen"` or the user's known static IPs.
   If 陈宇明 is going to access remotely from the hospital, his IP
   needs adding too.
2. **Generate htpasswd entry for the admin realm** (or reuse ops creds):
   `sudo htpasswd /etc/nginx/htpasswd admin` (uses existing file).
3. **Drop the vhost into `/etc/nginx/sites-available/`** (or the equivalent
   path on the Tencent host — see RUNBOOK-subdomain-split.md for the
   exact location used by api/app/wiki/ops).
4. **Symlink to `sites-enabled/`** and reload:
   ```bash
   sudo ln -s /etc/nginx/sites-available/admin.doctoragentai.cn.conf \
              /etc/nginx/sites-enabled/admin.doctoragentai.cn.conf
   sudo nginx -t && sudo systemctl reload nginx
   ```
5. **Verify TLS works:**
   ```bash
   curl -I https://admin.doctoragentai.cn/healthz
   # expect: HTTP/2 200 with `ok` body — the only un-gated path
   ```
6. **Verify gates work** (from a NON-allowed IP):
   ```bash
   curl -sI https://admin.doctoragentai.cn/         # expect 403 (deny all)
   curl -sI https://admin.doctoragentai.cn/api/admin/overview  # expect 403
   ```
7. **Verify the admin SPA loads** (from your allowed IP, with htpasswd):
   - Browser → `https://admin.doctoragentai.cn` → basic-auth prompt → SPA loads
   - Click 全体医生, 仪表盘, etc. — all four 概览 pages render
   - Network tab: every `/api/admin/*` is same-origin to `admin.*` (NOT api.*)
8. **Add `admin.doctoragentai.cn` to FastAPI's CORS allowlist** as
   belt-and-suspenders for any cross-origin SPA assets pulled from
   app.* — only needed if you observe CORS failures in step 7.
9. **Add the api.\* → admin.\* redirect** for `/api/admin/*`. Reload nginx.
10. **Hand off the URL to 陈宇明** with a one-liner explaining basic auth + token.

## Rollback

If anything goes wrong:

```bash
# Remove the new vhost
sudo rm /etc/nginx/sites-enabled/admin.doctoragentai.cn.conf
sudo nginx -t && sudo systemctl reload nginx
```

The old `https://api.doctoragentai.cn/api/admin/*` path still works
(now properly auth-gated by `Depends(require_admin_role)`). No data is
lost. The redirect added in step 9 is the only piece that needs reverting
separately.

## Validation tests

Add to `tests/test_admin_endpoints_authenticated.py` (or a new file
`tests/test_admin_subdomain.py`) once the host is live:

```python
def test_admin_subdomain_serves_endpoints(prod_client_admin):
    """admin.* serves /api/admin/* — same auth contract as api.*"""
    # No token → 401
    # Bogus token → 401
    # Super token → 200
```

This is integration; we can also add a manual probe to
`scripts/validate-prod-admin.sh` that the deploy step runs after each
release.

## Open questions

- **Does the partner doctor need a static IP at the hospital?** If they're
  on a dynamic IP, the IP allowlist becomes a maintenance burden. Falling
  back to "basic auth + admin token" without the IP gate is acceptable
  (still defense in depth). We could also issue them a per-user nginx
  basic-auth credential and rotate quarterly.

- **Should 系统 / 审计 admin sub-routes ever be reachable from api.\* even
  AFTER the move?** No — once admin.\* is live, the api.* /api/admin/*
  redirect is permanent. Bookmarks survive via 301.

- **Per-host cert vs wildcard?** Stay on the wildcard until / unless
  there's a security or regulatory reason to split. The wildcard is one
  rotation-per-year; a separate cert is one more thing to forget.

## Estimated effort

~4 hours total, sequenced:

| Step | Time |
|---|---|
| IP allowlist values + htpasswd | 10 min |
| Drop in vhost, reload, verify TLS | 30 min |
| Verify gates from non-allowed IP | 20 min |
| SPA load verification + click-through | 30 min |
| api.* → admin.* redirect | 15 min |
| Documentation update (RUNBOOK + CLAUDE.md) | 30 min |
| Buffer for issues | ~90 min |
