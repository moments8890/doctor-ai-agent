# DBGate — Browser DB Admin on Tencent

DBGate is an OSS web-based database client (MySQL, Postgres, SQLite,
Mongo, more). We self-host on the Tencent CVM so we can inspect prod
data, browse schema + relationships, and run ad-hoc queries from a
browser without exposing MySQL to the internet.

**Network shape**: web UI bound to `127.0.0.1:8101` only. External
access via SSH tunnel (recommended) or nginx reverse proxy under a
protected subpath (`/dbgate/`). DBGate has its own login page — no
nginx basic-auth layer needed, but keep the password strong.

**Storage footprint**: ~350MB image, ~150MB RAM steady. `dbgate_data`
volume stays tiny (only saved queries + UI prefs; connections come
from compose env).

**Registry mirror (China-friendly)**: `docker.io` is GFW-unreliable
from this VM. Compose uses `docker.1ms.run/dbgate/dbgate:latest`. If
you move off Tencent, swap back to `docker.io/dbgate/dbgate`.

**Secrets file**: stored in `/home/ubuntu/dbgate/dbgate.secrets` (not
the Docker-default `.env` name — mirrors the `glitchtip.secrets`
convention). Passed to compose via `docker compose --env-file
dbgate.secrets ...`.

**MySQL connectivity**: the backend MySQL is on the host at
`127.0.0.1:3306`. DBGate runs in Docker and reaches the host via
`host.docker.internal`, resolved through the `host-gateway` alias in
`extra_hosts`. This works on Tencent's docker-ce 20.10+.

---

## One-time setup

### 1. Create a dedicated MySQL user for DBGate

Don't point DBGate at the app's write user. Make a scoped user so a
stray UI click can't drop a table.

```bash
ssh tencent
# Log in to MySQL as a user that can GRANT (usually root).
mysql -u root -p
```

```sql
-- Read-only (default, recommended). Covers schema + data + EXPLAIN.
CREATE USER 'dbgate_reader'@'%' IDENTIFIED BY 'PASTE_STRONG_RANDOM_HERE';
GRANT SELECT, SHOW VIEW, PROCESS, REFERENCES ON doctor_ai.* TO 'dbgate_reader'@'%';
FLUSH PRIVILEGES;
```

If you later need write access from the UI (careful — full `DELETE`
power via a web app is real risk), add:

```sql
GRANT INSERT, UPDATE, DELETE ON doctor_ai.* TO 'dbgate_reader'@'%';
FLUSH PRIVILEGES;
```

The `'%'` host is required because the connection arrives via
`host-gateway` which is not `localhost` from MySQL's perspective.
Bind-address in MySQL must allow it — the CVM's MySQL typically listens
on `127.0.0.1` only, which blocks this. See "Known issues" at the
bottom for the two fixes.

### 2. Copy the compose file + create `dbgate.secrets`

```bash
ssh tencent
sudo mkdir -p /home/ubuntu/dbgate
sudo chown ubuntu:ubuntu /home/ubuntu/dbgate
cd /home/ubuntu/dbgate

# Copy compose from the repo checkout (gitee webhook keeps it current).
cp /home/ubuntu/doctor-ai-agent/deploy/tencent/dbgate/docker-compose.yml .

# Generate a DBGate UI password and write dbgate.secrets (NEVER commit).
cat > dbgate.secrets <<EOF
DBGATE_LOGIN=admin
DBGATE_PASSWORD=$(openssl rand -base64 24 | tr -d '\n' | tr -d '=')
DBGATE_MYSQL_USER=dbgate_reader
DBGATE_MYSQL_PASSWORD=PASTE_FROM_STEP_1
DBGATE_MYSQL_DB=doctor_ai
DBGATE_READ_ONLY=true
# Leave WEB_ROOT empty while using SSH tunnel. Set to "/dbgate" only
# when you wire up the nginx subpath (Day-2 section).
DBGATE_WEB_ROOT=
EOF
chmod 600 dbgate.secrets
```

### 3. Bring up the stack

```bash
docker compose --env-file dbgate.secrets up -d
docker compose ps
# Expect 1 container (dbgate) in Up state.
docker compose logs -f dbgate | head -30
# Expect: "app listening on port 3000" (or similar) — no stack trace.
```

### 4. Verify the web UI responds locally

```bash
curl -fsS -u "admin:$(grep DBGATE_PASSWORD dbgate.secrets | cut -d= -f2-)" \
  http://127.0.0.1:8101/ | head -5
# Should return HTML (not 401).
```

### 5. Access the UI from your laptop via SSH tunnel

On your **local machine**:
```bash
ssh -L 8101:127.0.0.1:8101 tencent
# keep this open
```

Open <http://localhost:8101> in your browser. Log in with
`admin` + the password from `dbgate.secrets`. You should see the
preset `doctor-ai (prod)` connection in the left tree — click to
expand, and schema browsing works immediately.

### 6. Smoke-test the connection

In DBGate left tree: `doctor-ai (prod)` → `doctor_ai` → `Tables` →
`medical_records` → right-click → "Open data". You should see rows.
If it says "Access denied" or "Unknown database", check:

1. MySQL bind-address allows non-loopback (see Known issues).
2. `dbgate_reader` was granted on `doctor_ai.*` specifically, not
   `some_other_db.*`.
3. `host.docker.internal` resolves from inside the container:
   `docker compose exec dbgate sh -c 'getent hosts host.docker.internal'`
   should return the host IP (usually `172.17.0.1`).

---

## Day-2 ops

### Restart / upgrade

```bash
cd /home/ubuntu/dbgate
docker compose pull
docker compose --env-file dbgate.secrets up -d
```

### View logs

```bash
docker compose logs -f dbgate
# Query errors + connection failures show up here.
```

### Back up saved queries (light)

```bash
docker run --rm -v dbgate_dbgate_data:/data -v /home/ubuntu/dbgate/backups:/backup \
  alpine tar czf /backup/dbgate-$(date +%Y%m%d).tgz -C /data .
```

### Rotate the UI password

```bash
# Edit /home/ubuntu/dbgate/dbgate.secrets — change DBGATE_PASSWORD.
cd /home/ubuntu/dbgate
docker compose --env-file dbgate.secrets up -d   # recreate with new env
```

### Add a second connection (e.g. Mongo, another MySQL)

Extend the `environment:` block in `docker-compose.yml` following the
same `CONNECTIONS=con1,con2` + per-connection env-var pattern used for
`doctorai`. DBGate picks up additions on container restart.

### Public access via nginx subpath (`/dbgate/`)

DBGate supports subpath hosting via `WEB_ROOT`. Unlike GlitchTip it
does NOT need `sub_filter` rewrites — the built-in env var handles
asset paths. Two steps:

**Step 1 — flip `WEB_ROOT` on and recreate:**

```bash
# Edit /home/ubuntu/dbgate/dbgate.secrets
DBGATE_WEB_ROOT=/dbgate

cd /home/ubuntu/dbgate
docker compose --env-file dbgate.secrets up -d
```

**Step 2 — add the nginx location block.** Insert into
`/etc/nginx/sites-enabled/doctoragentai.cn` inside the `listen 443 ssl`
server block, BEFORE the catch-all `location /`:

```nginx
location /dbgate/ {
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /dbgate;

    # DBGate streams query results over WebSocket — must upgrade.
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    # Long queries against prod DB can take a while — generous timeout.
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    proxy_pass http://127.0.0.1:8101/;
}
```

`sudo nginx -t && sudo systemctl reload nginx`.

Then hit <https://api.doctoragentai.cn/dbgate/> and log in.

**If the SPA loads but static assets 404**, DBGate's `WEB_ROOT` didn't
take effect for your image version. Fall back to the GlitchTip-style
`sub_filter` rewrite — see `glitchtip.md` for the exact template and
remember `proxy_set_header Accept-Encoding ""`.

#### Footgun — stale server blocks in sites-enabled/

Same gotcha as GlitchTip. If `curl https://api.doctoragentai.cn/dbgate/`
returns the main frontend's HTML, check `ls /etc/nginx/sites-enabled/`
for stale backups masking the canonical config. Fix in
`glitchtip.md` → "Footgun — stale server blocks".

---

## Teardown (reversible)

```bash
cd /home/ubuntu/dbgate
docker compose down -v          # -v drops saved queries → full reset
sudo rm -rf /home/ubuntu/dbgate # optional — compose file + secrets
# Remove the MySQL user:
mysql -u root -p -e "DROP USER 'dbgate_reader'@'%'; FLUSH PRIVILEGES;"
```

No changes to app schema or data. Zero impact on the backend.

---

## Known issues

### MySQL `bind-address` blocks docker-gateway connections

Default Tencent CVM MySQL listens on `127.0.0.1` only. DBGate's
connection arrives from the docker bridge (typically `172.17.0.1`
from MySQL's POV) — blocked.

**Option A (simplest, MySQL-in-Docker setups):** move MySQL into the
same docker-compose as DBGate. They share a docker network and MySQL
stays loopback-only from the host's POV.

**Option B (host MySQL):** extend `bind-address` to also accept the
docker bridge:

```bash
sudo vim /etc/mysql/mysql.conf.d/mysqld.cnf
# Change: bind-address = 127.0.0.1
# To:     bind-address = 127.0.0.1,172.17.0.1
# (MySQL 8.0.13+ supports comma-separated. Older: use 0.0.0.0 AND
#  firewall off port 3306 from the internet — CVM SG + ufw.)
sudo systemctl restart mysql
```

Verify the firewall still blocks 3306 externally:

```bash
sudo ss -ltnp | grep 3306
# Expect: 127.0.0.1:3306 AND 172.17.0.1:3306. Never 0.0.0.0:3306 publicly.
ufw status                              # if ufw is enabled
# CVM Security Group — confirm port 3306 ingress is denied from 0.0.0.0/0.
```

### "Read-only mode" doesn't prevent schema DDL in DBGate UI

`READ_ONLY_doctorai=true` blocks DML (INSERT/UPDATE/DELETE) in the UI,
but DBGate may still let you *try* a `DROP TABLE` — it'll fail at the
MySQL level because `dbgate_reader` doesn't have the privilege. Belt
and braces: the MySQL GRANT is the real gate; the DBGate flag is UI
affordance. Don't rely on the flag alone.

### Connection preset password is visible in `docker inspect`

Anyone with `docker` group membership on the CVM can see the MySQL
password via `docker inspect dbgate`. Today that's just you, but if
that changes, switch to docker secrets or bind-mount a JSON connection
file (DBGate supports `CONNECTIONS_FILE=/path/to/connections.json`).

### Subpath asset loading depends on DBGate version

`WEB_ROOT` has moved around across DBGate versions. If the subpath
deploy serves blank pages or missing assets, pin to a known-good tag
(e.g. `dbgate/dbgate:6.0.0`) instead of `:latest`, or fall back to the
GlitchTip-style `sub_filter` rewrite.
