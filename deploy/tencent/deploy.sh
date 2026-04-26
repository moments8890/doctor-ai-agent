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

# Pin current SHA as a systemd env var so Sentry/GlitchTip `release` tag
# attributes events to the exact deployed commit. Enables regression
# attribution when comparing error rates across deploys.
GIT_COMMIT=$(git rev-parse HEAD)
sudo mkdir -p /etc/systemd/system/doctor-ai-backend.service.d
sudo tee /etc/systemd/system/doctor-ai-backend.service.d/release.conf >/dev/null <<EOF
[Service]
Environment=GIT_COMMIT=${GIT_COMMIT}
EOF
sudo systemctl daemon-reload

# Python deps
"$VENV/bin/pip" install -q -r requirements.txt

# Alembic migrations (idempotent — no-op when DB already at head). Runs
# after pip install so any new SQLAlchemy/driver deps are available.
# Note: /home/ubuntu/deploy.sh is a symlink to this file, so edits to
# deploy/tencent/deploy.sh in-repo auto-propagate via git reset above.
ENVIRONMENT=production PYTHONPATH="$APP_DIR/src" "$VENV/bin/alembic" upgrade head

# Frontend build (package.json is in frontend/web/). Note: the prebuild
# script in package.json runs scripts/sync-internal-wiki-docs.sh first,
# so wiki.* internal docs always reflect the latest committed .md.
#
# VITE_API_BASE_URL: app.doctoragentai.cn deliberately has no /api/ proxy
# (see deploy/tencent/nginx/app.doctoragentai.cn.conf header), so the SPA
# must hit api.* cross-origin. Without this var, every /api/* call falls
# into the SPA fallback and POSTs return 405 Not Allowed from nginx.
# Inlined here rather than in a .env.production file so the deploy
# script remains the single source of truth for prod-build-time config.
cd "$APP_DIR/frontend/web"
npm ci --silent
VITE_API_BASE_URL=https://api.doctoragentai.cn npm run build
rm -rf "$APP_DIR/frontend/dist"
cp -r "$APP_DIR/frontend/web/dist" "$APP_DIR/frontend/dist"
chmod -R o+rX "$APP_DIR/frontend/dist"
cd "$APP_DIR"

# Nuke Python bytecode cache so a fresh import picks up the new code.
# Python's mtime-based .pyc invalidation has been observed to miss the
# update when git-pull + restart land within the same second; doing it
# unconditionally is cheap and removes the failure mode.
find "$APP_DIR/src" -type d -name __pycache__ -prune -exec rm -rf {} +

# Restart backend (systemd uses cli.py start --prod)
sudo systemctl restart doctor-ai-backend

echo "=== deploy finished at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
