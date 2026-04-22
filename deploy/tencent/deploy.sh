#!/usr/bin/env bash
# deploy.sh — pull latest, rebuild frontend, restart backend via cli.py
# Called by webhook_server.py on Gitee push events.
set -euo pipefail

APP_DIR="/home/ubuntu/doctor-ai-agent"
VENV="$APP_DIR/.venv"
LOG="$APP_DIR/logs/deploy.log"

exec >> "$LOG" 2>&1
echo "=== deploy started at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

cd "$APP_DIR"

# Pull latest (from gitee — webhook triggers on gitee push)
git fetch gitee
git reset --hard gitee/main

# Python deps
"$VENV/bin/pip" install -q -r requirements.txt

# Alembic migrations (idempotent — no-op when DB already at head). Runs
# after pip install so any new SQLAlchemy/driver deps are available.
# Note: /home/ubuntu/deploy.sh is a symlink to this file, so edits to
# deploy/tencent/deploy.sh in-repo auto-propagate via git reset above.
ENVIRONMENT=production PYTHONPATH="$APP_DIR/src" "$VENV/bin/alembic" upgrade head

# Frontend build (package.json is in frontend/web/)
cd "$APP_DIR/frontend/web"
npm ci --silent
npm run build
rm -rf "$APP_DIR/frontend/dist"
cp -r "$APP_DIR/frontend/web/dist" "$APP_DIR/frontend/dist"
chmod -R o+rX "$APP_DIR/frontend/dist"
cd "$APP_DIR"

# Restart backend (systemd uses cli.py start --prod)
sudo systemctl restart doctor-ai-backend

echo "=== deploy finished at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
