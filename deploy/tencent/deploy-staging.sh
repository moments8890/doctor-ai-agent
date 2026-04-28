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
