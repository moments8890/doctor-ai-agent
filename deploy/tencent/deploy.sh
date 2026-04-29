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

# Pull latest (from gitee — webhook triggers on gitee push).
# Branch model (post 2026-04-28 swap):
#   gitee/main    → daily trunk; auto-deploys to staging via deploy-staging.sh
#   gitee/tencent → prod-only release pointer; pushed deliberately to ship.
git fetch gitee
git reset --hard gitee/tencent

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

# Atomic swap of frontend/dist via stage-then-rename. Replaces the older
# `rm -rf $APP_DIR/frontend/dist` + `cp -r` pattern, which left the
# pipeline jammed for ~4 hours on 2026-04-26 after dist files ended up
# root-owned (probably from a manual `sudo bash deploy.sh` recovery run):
# every subsequent ubuntu-user deploy aborted at the rm step and never
# reached `systemctl restart`, so prod ran stale code that was missing
# the latest schema.
#
# Why this is robust: only the parent dir (`frontend/`) needs to be
# ubuntu-writable, not the dist contents. The `mv` of an existing dir to
# a new name only touches the parent's directory entry, so it works
# regardless of whose UID owns the files inside. Any prior staging
# dirs from earlier failed runs are cleaned up before the cp so a
# half-finished previous run can't cause `cp -r` to nest.
NEW_DIST="$APP_DIR/frontend/dist.new.$$"
OLD_DIST="$APP_DIR/frontend/dist.old.$$"
rm -rf "$NEW_DIST" "$OLD_DIST" 2>/dev/null || true
cp -r "$APP_DIR/frontend/web/dist" "$NEW_DIST"
chmod -R o+rX "$NEW_DIST"
[ -e "$APP_DIR/frontend/dist" ] && mv "$APP_DIR/frontend/dist" "$OLD_DIST"
mv "$NEW_DIST" "$APP_DIR/frontend/dist"
# Best-effort cleanup of the old tree. Silently no-ops on root-owned
# stragglers; those accumulate under `frontend/dist.old.*` for a human
# (or a future privileged sweeper) to reap.
rm -rf "$OLD_DIST" 2>/dev/null || true

cd "$APP_DIR"

# Nuke Python bytecode cache so a fresh import picks up the new code.
# Python's mtime-based .pyc invalidation has been observed to miss the
# update when git-pull + restart land within the same second; doing it
# unconditionally is cheap and removes the failure mode.
find "$APP_DIR/src" -type d -name __pycache__ -prune -exec rm -rf {} +

# Restart backend (systemd uses cli.py start --prod)
sudo systemctl restart doctor-ai-backend

echo "=== deploy finished at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
