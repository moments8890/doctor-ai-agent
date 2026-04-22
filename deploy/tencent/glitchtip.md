# GlitchTip — Self-Hosted Error Tracking on Tencent

GlitchTip is an OSS, Sentry-SDK-compatible error tracker. We self-host
on the Tencent CVM because Sentry.io SaaS is unreliable from mainland
China and we already have Docker on this VM (`n8n`, `doctor-ai-mysql`).

**Network shape**: web UI bound to `127.0.0.1:8100` only. External
access via SSH tunnel (easiest) or nginx reverse proxy under a
protected subpath (`/glitchtip/`).

**Storage footprint**: ~600MB images, ~200MB RAM steady, postgres data
grows with event volume (estimate 10MB/1k events). Prune policy: 30d
rolling by default, configurable in GlitchTip settings.

**Registry mirrors (China-friendly)**: `docker.io` is GFW-unreliable
from this VM, so the compose uses:
- `mirror.ccs.tencentyun.com/library/*` — Tencent's official-image
  mirror (postgres, redis).
- `docker.1ms.run/*` — public Chinese mirror for third-party images
  (glitchtip). Same namespace as docker.io.

If you ever move off Tencent to a non-China host, swap these back to
`docker.io` equivalents.

**Secrets file**: stored in `/home/ubuntu/glitchtip/glitchtip.secrets`
(not the Docker-default `.env` name — this keeps our repo's hook
guard clean and makes the file's purpose obvious). Passed to compose
via `docker compose --env-file glitchtip.secrets ...`.

---

## One-time setup

### 1. Copy the compose file + create `glitchtip.secrets`

```bash
ssh tencent
sudo mkdir -p /home/ubuntu/glitchtip
sudo chown ubuntu:ubuntu /home/ubuntu/glitchtip
cd /home/ubuntu/glitchtip

# Copy compose from the repo checkout (/home/ubuntu/doctor-ai-agent is
# already kept current via the gitee webhook)
cp /home/ubuntu/doctor-ai-agent/deploy/tencent/glitchtip/docker-compose.yml .

# Generate two secrets and write glitchtip.secrets (NEVER commit).
# Postgres password — any strong random string, 32+ chars.
# SECRET_KEY — Django requires >=50 chars, use `openssl rand -base64 50`.
cat > glitchtip.secrets <<EOF
POSTGRES_PASSWORD=$(openssl rand -hex 24)
GLITCHTIP_SECRET_KEY=$(openssl rand -base64 50 | tr -d '\n' | tr -d '=')
GLITCHTIP_DOMAIN=http://127.0.0.1:8100
GLITCHTIP_FROM_EMAIL=glitchtip@doctoragentai.cn
EOF
chmod 600 glitchtip.secrets
```

### 2. Bring up the stack

```bash
docker compose --env-file glitchtip.secrets up -d
# Wait for postgres + redis healthy
docker compose ps
# Expect 4 containers, web + worker Up, postgres + redis Up (healthy)
```

### 3. Run migrations + create superuser

GlitchTip runs Django migrations automatically on container start if
the DB is fresh. Verify and create the admin user:

```bash
docker compose exec web ./manage.py migrate --check
docker compose exec web ./manage.py createsuperuser
# Follow prompts: email + password. This is the admin login.
```

### 4. Verify web UI is responding

```bash
curl -fsS http://127.0.0.1:8100/api/0/ | head -5
# Should return JSON with "version" + "user" fields
```

### 5. Access the UI from your laptop via SSH tunnel

On your **local machine**:
```bash
ssh -L 8100:127.0.0.1:8100 tencent
# keep this open
```

Then open <http://localhost:8100> in your browser. Log in as the
superuser created in step 3.

### 6. Create your first project in the UI

1. Dashboard → **New Project**
2. Platform: **Python / FastAPI**
3. Name: `doctor-ai-backend`
4. Copy the DSN it generates — looks like
   `http://<public_key>@127.0.0.1:8100/1`

### 7. Wire the backend to GlitchTip

`_init_sentry()` at `src/main.py:91` already reads `SENTRY_DSN` — no
code change needed.

```bash
# On prod — inject the DSN via a systemd drop-in so it survives restarts
sudo mkdir -p /etc/systemd/system/doctor-ai-backend.service.d
sudo tee /etc/systemd/system/doctor-ai-backend.service.d/sentry.conf <<'EOF'
[Service]
Environment=SENTRY_DSN=http://PASTE_DSN_HERE@127.0.0.1:8100/1
Environment=SENTRY_TRACES_RATE=0.1
EOF
sudo systemctl daemon-reload
sudo systemctl restart doctor-ai-backend
```

Backend logs will show `[Sentry] initialized` on startup when the DSN
is loaded.

### 8. Send a test exception

Easiest way: trigger a real 500 by hitting an endpoint that will fail.
You can also use the Python SDK's explicit capture:

```bash
docker exec -it doctor-ai-backend /bin/true   # backend not in docker — use systemd instead
# Or from the backend's Python shell:
ssh tencent
cd /home/ubuntu/doctor-ai-agent
ENVIRONMENT=production PYTHONPATH=src .venv/bin/python -c "
import sentry_sdk, os
from src.main import _init_sentry
os.environ['SENTRY_DSN'] = 'PASTE_DSN_HERE'
_init_sentry()
try:
    raise RuntimeError('glitchtip smoke test — ok to ignore')
except Exception as e:
    sentry_sdk.capture_exception(e)
    sentry_sdk.flush(timeout=5)
print('sent')
"
```

Check the GlitchTip UI (via SSH tunnel) — event should appear within
5 seconds under `doctor-ai-backend → Issues`.

---

## Day-2 ops

### Restart / upgrade

```bash
cd /home/ubuntu/glitchtip
docker compose pull           # pull latest glitchtip/glitchtip image
docker compose --env-file glitchtip.secrets up -d          # recreate web + worker
docker compose exec web ./manage.py migrate  # apply any GlitchTip migrations
```

### View logs

```bash
docker compose logs -f web worker
# errors in GlitchTip itself (not your app's events) show up here
```

### Backup postgres

```bash
docker compose exec postgres pg_dump -U glitchtip glitchtip | gzip > \
  /home/ubuntu/glitchtip/backups/$(date +%Y%m%d).sql.gz
```

### Rotate the DSN

If the DSN is ever leaked: in the GlitchTip UI → Project Settings →
Client Keys → revoke + regenerate → update the systemd drop-in →
`daemon-reload` + `restart doctor-ai-backend`.

### Turn off new organization creation

After the first org is set up, flip the flag to prevent random signups
(relevant if you ever expose the UI publicly):

```bash
# Edit /home/ubuntu/glitchtip/glitchtip.secrets
GLITCHTIP_ENABLE_ORG_CREATION=false
# Then
cd /home/ubuntu/glitchtip
docker compose --env-file glitchtip.secrets up -d          # recreate containers with new env
```

### Public access via nginx (optional, DO LATER)

If you want the UI reachable without SSH tunnel, add this block to
`/etc/nginx/sites-enabled/doctoragentai.cn` inside the `listen 443 ssl`
server and reload nginx. **Only do this after you've secured login +
rotated the SECRET_KEY + confirmed the only accounts are yours.**

```nginx
location /glitchtip/ {
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass http://127.0.0.1:8100/;
}
```

Then update `GLITCHTIP_DOMAIN=https://api.doctoragentai.cn/glitchtip`
in `.env` + `docker compose --env-file glitchtip.secrets up -d` so GlitchTip generates correct
absolute URLs in invite emails + DSN hostnames.

---

## Teardown (reversible)

```bash
cd /home/ubuntu/glitchtip
docker compose down -v        # -v drops the postgres volume → full reset
sudo rm -rf /home/ubuntu/glitchtip  # optional — compose file + .env
# Remove SENTRY_DSN env:
sudo rm /etc/systemd/system/doctor-ai-backend.service.d/sentry.conf
sudo systemctl daemon-reload && sudo systemctl restart doctor-ai-backend
```

No schema changes to our app DB. Backend falls back to no-op Sentry
init (see `_init_sentry()` — `if not dsn: return`). Zero downtime.

---

## Known issues

- **Initial postgres init takes ~20s** on first `docker compose --env-file glitchtip.secrets up -d` —
  web + worker restart-loop until healthcheck passes. Harmless.
- **`consolemail://` means no real emails**. Invite links + password
  resets print to `docker compose logs worker`. Set `EMAIL_URL` to a
  real SMTP if you want delivered email.
- **DSN points at `127.0.0.1`** — this works because both GlitchTip and
  the backend run on the same VM. Docker network isolation does NOT
  affect the backend since it's a systemd service on the host, not in
  docker. If you later containerize the backend, DSN needs to change to
  an internal docker hostname.
