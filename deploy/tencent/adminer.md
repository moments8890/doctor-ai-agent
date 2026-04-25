# Adminer — Browser DB Admin on Tencent

Adminer is a single-PHP-binary OSS web DB client (supports MySQL,
Postgres, SQLite, etc.). We self-host on the Tencent CVM so we can
inspect prod data, browse schema + FK relationships, and run ad-hoc
queries from a browser without exposing MySQL to the internet.

**URL**: `https://ops.doctoragentai.cn/dbgate/` (subpath preserved from
the original DBGate deploy — see "Why not DBGate?" below).

**Network shape**: service bound to `127.0.0.1:8101` only; public
access via nginx subpath under `/dbgate/`.

**Storage footprint**: ~40MB image, negligible RAM, no volume required.

**Why not DBGate?** Our first choice was DBGate for the ER-diagram
feature. DBGate 6.7+ and 7.x moved to JWT-token auth that always
requires an `Authorization: Bearer <token>` header, including on the
root UI. Can't be disabled via env var and doesn't accept HTTP basic
auth. Doesn't fit behind a simple nginx-basic-auth gate. Adminer trades
ER diagrams for a plain HTTP login form that behaves as expected.

**Auth layers (defense in depth)**:
1. **nginx basic auth** — first gate, before Adminer renders anything.
2. **Adminer's login form** — per-session MySQL credentials (server,
   username, password, database).
3. **MySQL GRANT** — `dbgate_reader` has only `SELECT, SHOW VIEW,
   REFERENCES ON doctor_ai.*` — even a stolen session can't write.

**Secrets file**: `/home/ubuntu/dbgate/dbgate.secrets` on server.
Passwords mirrored to `~/.config/doctor-ai-agent/dbgate.secrets` on
your laptop (both chmod 600).

---

## One-time setup

### 1. Create shared docker network + attach doctor-ai-mysql

```bash
ssh tencent
docker network create dbgate_net
docker network connect dbgate_net doctor-ai-mysql
docker inspect doctor-ai-mysql --format \
  '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} IP={{$v.IPAddress}}{{println}}{{end}}'
# Expect: bridge + dbgate_net
```

### 2. Create `dbgate_reader` MySQL user

```bash
MYSQL_PWD='<root-password-from-docker-inspect>' docker exec -i -e MYSQL_PWD \
  doctor-ai-mysql mysql -u root <<'SQL'
CREATE USER IF NOT EXISTS 'dbgate_reader'@'%' IDENTIFIED BY 'PASTE_STRONG_RANDOM_HERE';
GRANT SELECT, SHOW VIEW, REFERENCES ON doctor_ai.* TO 'dbgate_reader'@'%';
FLUSH PRIVILEGES;
SQL
```

**Note**: `PROCESS` is global-only in MySQL 8 — can't be mixed with
DB-scoped GRANTs in one statement. If you want `SHOW PROCESSLIST` in
the UI: `GRANT PROCESS ON *.* TO 'dbgate_reader'@'%';` separately.

### 3. Copy compose + write `dbgate.secrets`

```bash
ssh tencent
sudo mkdir -p /home/ubuntu/dbgate
sudo chown ubuntu:ubuntu /home/ubuntu/dbgate
cd /home/ubuntu/dbgate

cp /home/ubuntu/doctor-ai-agent/deploy/tencent/adminer/docker-compose.yml .

cat > dbgate.secrets <<EOF
DBGATE_LOGIN=admin
DBGATE_PASSWORD=$(openssl rand -base64 24 | tr -d '=/+\n' | head -c 32)
DBGATE_MYSQL_USER=dbgate_reader
DBGATE_MYSQL_PASSWORD=PASTE_FROM_STEP_2
DBGATE_MYSQL_DB=doctor_ai
EOF
chmod 600 dbgate.secrets
```

### 4. Bring up the stack

```bash
docker compose --env-file dbgate.secrets up -d
docker compose ps
# Expect: adminer Up on 127.0.0.1:8101
```

### 5. Create nginx htpasswd

```bash
DBG_PASS=$(grep '^DBGATE_PASSWORD=' /home/ubuntu/dbgate/dbgate.secrets | cut -d= -f2-)
HASH=$(openssl passwd -apr1 "$DBG_PASS")
echo "admin:$HASH" | sudo tee /etc/nginx/.dbgate-htpasswd >/dev/null
sudo chmod 640 /etc/nginx/.dbgate-htpasswd
sudo chown root:www-data /etc/nginx/.dbgate-htpasswd
```

### 6. Add nginx location block

Insert into `/etc/nginx/sites-enabled/doctoragentai.cn` inside the
`listen 443 ssl` server block, BEFORE the catch-all `location /`:

```nginx
location /dbgate/ {
    auth_basic "Doctor-AI DB Admin";
    auth_basic_user_file /etc/nginx/.dbgate-htpasswd;

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /dbgate;

    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_pass http://127.0.0.1:8101/;
}
```

`sudo nginx -t && sudo systemctl reload nginx`.

### 7. Mirror secrets to your laptop

```bash
# On your laptop:
mkdir -p ~/.config/doctor-ai-agent
scp tencent:/home/ubuntu/dbgate/dbgate.secrets ~/.config/doctor-ai-agent/dbgate.secrets
chmod 600 ~/.config/doctor-ai-agent/dbgate.secrets
```

### 8. Log in

1. Browser: <https://ops.doctoragentai.cn/dbgate/>
2. **First prompt (nginx basic auth)**: username `admin`, password from
   `DBGATE_PASSWORD` in dbgate.secrets.
3. **Second screen (Adminer login form)**:
   - System: MySQL
   - Server: `doctor-ai-mysql` (prefilled)
   - Username: `dbgate_reader` (from `DBGATE_MYSQL_USER`)
   - Password: from `DBGATE_MYSQL_PASSWORD` in dbgate.secrets
   - Database: `doctor_ai`

You should see the schema tree with all 42+ tables in `doctor_ai`.
Read-only at the MySQL layer — any UPDATE/DELETE attempt returns
"access denied".

---

## Day-2 ops

### Restart / upgrade

```bash
cd /home/ubuntu/dbgate
docker compose pull
docker compose --env-file dbgate.secrets up -d
```

### Rotate the nginx-basic-auth password

```bash
cd /home/ubuntu/dbgate
NEW_PASS=$(openssl rand -base64 32 | tr -d '=/+\n' | head -c 32)

python3 - <<PYEOF
from pathlib import Path
f = Path('dbgate.secrets')
out = [line if not line.startswith('DBGATE_PASSWORD=')
       else f'DBGATE_PASSWORD=${NEW_PASS}'
       for line in f.read_text().splitlines()]
f.write_text('\n'.join(out) + '\n')
PYEOF

HASH=$(openssl passwd -apr1 "$NEW_PASS")
echo "admin:$HASH" | sudo tee /etc/nginx/.dbgate-htpasswd >/dev/null

# Re-mirror to laptop
# scp tencent:/home/ubuntu/dbgate/dbgate.secrets ~/.config/doctor-ai-agent/
```

### Rotate the `dbgate_reader` MySQL password

```bash
cd /home/ubuntu/dbgate
NEW_DB_PASS=$(openssl rand -base64 32 | tr -d '=/+\n' | head -c 32)

MYSQL_PWD='<root-password>' docker exec -i -e MYSQL_PWD doctor-ai-mysql \
  mysql -u root -e "ALTER USER 'dbgate_reader'@'%' IDENTIFIED BY '$NEW_DB_PASS'; FLUSH PRIVILEGES;"
```

---

## Teardown (reversible)

```bash
cd /home/ubuntu/dbgate
docker compose down
sudo rm -rf /home/ubuntu/dbgate
docker network rm dbgate_net 2>/dev/null  # OK if fails — doctor-ai-mysql may still be on it
mysql -u root -p -e "DROP USER 'dbgate_reader'@'%'; FLUSH PRIVILEGES;"

sudo rm /etc/nginx/.dbgate-htpasswd
# Delete the /dbgate/ block from /etc/nginx/sites-enabled/doctoragentai.cn
sudo nginx -t && sudo systemctl reload nginx
```

Zero impact on the backend or MySQL data.

---

## Known issues

### `host.docker.internal` doesn't work for dockerised MySQL

See `glitchtip.md` — same gotcha; the fix is the shared `dbgate_net`
network approach used in step 1.

### Adminer has no ER-diagram view

That was our original DBGate ask. Workarounds:
- SchemaSpy offline (generates static HTML ERD from a live DB).
- DBeaver CE desktop over an SSH tunnel to `127.0.0.1:3306`.
- Revisit DBGate if its auth story relaxes in a future version.

### Session cookies scoped to /dbgate/

Adminer sets `adminer_sid` and `adminer_key` cookies on `path=/`.
Under our subpath deploy, if you ever host another Adminer on the
same domain, their cookies would collide. Not a concern today.
