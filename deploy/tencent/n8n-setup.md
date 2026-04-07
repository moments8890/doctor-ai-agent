# n8n Setup on Tencent Cloud

n8n runs alongside the backend on `101.35.116.122` to simulate patient
messages for newly onboarded doctors.

## What it does

Every hour, the workflow:
1. Calls `GET /api/admin/doctors` to list all doctors
2. Filters for doctors created in the last 24 hours (uses `created_at`)
3. Deduplicates via n8n static data (won't re-seed the same doctor)
4. For each new doctor: registers a simulated patient, then sends 6 messages
   over 3 days with realistic wait intervals

## Prerequisites

- Docker installed on the host
- Backend running on `127.0.0.1:8000`
- Nginx configured with SSL on `api.doctoragentai.cn`

## Installation

### 1. Pull the n8n image (China mirror)

```bash
docker pull docker.1ms.run/n8nio/n8n:latest
```

Docker Hub is blocked from China. Use `docker.1ms.run` as a mirror.

### 2. Create data directory

```bash
mkdir -p /home/ubuntu/n8n-data
```

### 3. Start the container

```bash
docker run -d \
  --name n8n \
  --network host \
  --restart unless-stopped \
  -v /home/ubuntu/n8n-data:/home/node/.n8n \
  -e N8N_PORT=5678 \
  -e N8N_EDITOR_BASE_URL=https://api.doctoragentai.cn/n8n/ \
  -e N8N_PATH=/n8n/ \
  -e WEBHOOK_URL=https://api.doctoragentai.cn/n8n/ \
  -e GENERIC_TIMEZONE=Asia/Shanghai \
  -e TZ=Asia/Shanghai \
  docker.1ms.run/n8nio/n8n:latest
```

`--network host` lets n8n reach the backend at `127.0.0.1:8000`.

### 4. Set up the owner account

```bash
curl -X POST http://127.0.0.1:5678/rest/owner/setup \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@doctoragentai.cn","firstName":"Admin","lastName":"N8N","password":"<PASSWORD>"}'
```

### 5. Import the workflow

```bash
# Add an "id" field to the workflow JSON (n8n requires it)
python3 -c "
import json
with open('docs/dev/n8n-auto-sim.json') as f:
    wf = json.load(f)
wf['id'] = '1'
with open('/tmp/n8n-auto-sim.json', 'w') as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)
"

docker cp /tmp/n8n-auto-sim.json n8n:/tmp/n8n-auto-sim.json
docker exec n8n n8n import:workflow --input=/tmp/n8n-auto-sim.json
```

### 6. Activate the workflow

```bash
docker exec n8n n8n update:workflow --id=1 --active=true
docker restart n8n
```

The restart is needed because CLI changes don't take effect while n8n is running.

### 7. Add nginx proxy

Add this block to `/etc/nginx/sites-enabled/doctoragentai.cn`, **before** the
catch-all `location / {` block:

```nginx
    location /n8n/ {
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
        proxy_pass http://127.0.0.1:5678/;
    }
```

Then reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 8. Verify

```bash
# Local health check
curl http://127.0.0.1:5678/healthz

# Public access
curl https://api.doctoragentai.cn/n8n/healthz

# Check workflow is active
docker logs n8n 2>&1 | grep "Activated"
```

## Access

- URL: https://api.doctoragentai.cn/n8n/
- Email: `admin@doctoragentai.cn`
- Password: stored on the server, not in this repo

## Workflow source

`docs/dev/n8n-auto-sim.json`

## Data persistence

SQLite database at `/home/ubuntu/n8n-data/database.sqlite`. Workflow
definitions, execution history, and static data (dedup state) are stored here.

## Maintenance

```bash
# View logs
docker logs n8n --tail 50

# Restart
docker restart n8n

# Update n8n
docker pull docker.1ms.run/n8nio/n8n:latest
docker rm -f n8n
# Re-run the docker run command from step 3
```
