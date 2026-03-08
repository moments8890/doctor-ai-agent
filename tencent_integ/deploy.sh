#!/usr/bin/env bash
# deploy.sh — pull latest code from Gitee and restart the backend.
# Must be idempotent and safe to run concurrently (webhook_server holds a lock).
set -euo pipefail

APP_DIR="/home/ubuntu/doctor-ai-agent"
SERVICE="doctor-ai-backend"
VENV="$APP_DIR/.venv"
LOG="$APP_DIR/logs/deploy.log"

exec >> "$LOG" 2>&1
echo "=== deploy started at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

cd "$APP_DIR"

# Pull latest from Gitee (origin)
git fetch origin
git reset --hard origin/main

# Sync Python dependencies
"$VENV/bin/pip" install -q -r requirements.txt

# Restart backend via systemd
sudo systemctl restart "$SERVICE"

echo "=== deploy finished at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
