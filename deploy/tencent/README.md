# Tencent Cloud Deployment Artifacts

This folder contains the minimum production deployment artifacts for `doctor-ai-agent`.

## Files

- `docker-compose.prod.yml`: production compose spec (backend + frontend)
- `nginx.conf`: frontend nginx config (SPA + `/api` reverse proxy)
- `runtime.prod.example.json`: runtime config template (copy to server)
- `runtime.prod.mysql-single-node.example.json`: single-node MySQL runtime template

## Server Preparation

1. Install Docker Engine + Docker Compose plugin.
2. Create deployment directory (example): `/opt/doctor-ai-agent`.
3. Copy one runtime template to `/opt/doctor-ai-agent/config/runtime.prod.json` and replace all `replace_me` values.
4. If using single-node MySQL from compose, prefer:
   - `runtime.prod.mysql-single-node.example.json`
4. Ensure ports are open:
- `80` for frontend
- internal localhost `8000` for backend health checks

## Compose Run

```bash
cd /opt/doctor-ai-agent
export BACKEND_IMAGE="ccr.ccs.tencentyun.com/<namespace>/doctor-ai-agent-backend"
export FRONTEND_IMAGE="ccr.ccs.tencentyun.com/<namespace>/doctor-ai-agent-frontend"
export IMAGE_TAG="latest"
export MYSQL_ROOT_PASSWORD="<strong-root-password>"
export MYSQL_DATABASE="doctor_ai"
export MYSQL_USER="doctor_ai"
export MYSQL_PASSWORD="<strong-app-password>"

docker compose -f deploy/tencent/docker-compose.prod.yml pull
docker compose -f deploy/tencent/docker-compose.prod.yml up -d --remove-orphans
docker compose -f deploy/tencent/docker-compose.prod.yml ps
```

## Source Deploy on Ubuntu (No Backend/Frontend Containers)

If you want local source frontend/backend, local MySQL in Docker, and remote Tencent LKEAP/DeepSeek:

```bash
cd /opt/doctor-ai-agent
# one-time on a fresh VM
./dev.sh vm-bootstrap --with-frontend --with-mysql

# each time you start services
export TENCENT_LKEAP_API_KEY="<your_tencent_lkeap_key>"
# optional: use a specific model enabled in your Tencent account
export TENCENT_LKEAP_MODEL="deepseek-v3-1"
./dev.sh vm-up --llm-provider tencent_lkeap
```

Stop services:

```bash
./dev.sh vm-down
```

## GitHub Secrets Required by `deploy-prod.yml`

- `TCR_REGISTRY`
- `TCR_USERNAME`
- `TCR_PASSWORD`
- `TCR_IMAGE_PREFIX` (example: `ccr.ccs.tencentyun.com/<namespace>/doctor-ai-agent`)
- `PROD_HOST`
- `PROD_USER`
- `PROD_SSH_PRIVATE_KEY`
- `PROD_DEPLOY_DIR` (example: `/opt/doctor-ai-agent`)

## Post-Deploy Checks

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -I http://127.0.0.1/
```
