#!/usr/bin/env bash
# auto_deploy_on_drift.sh — fallback for silently-dropped gitee webhooks.
#
# Polls gitee/main every cron tick. If it diverges from the deployed HEAD
# and the latest commit is at least MIN_AGE_SEC old (so we don't race a
# webhook-triggered deploy that's already in flight), runs deploy.sh.
#
# Coexists with deploy/tencent/drift_check.sh, which only alarms.
# This one self-heals: gitee webhook becomes a nice-to-have, not load-bearing.
#
# Wire-up (already done on prod, but for reference):
#   crontab -e (as ubuntu)
#   */5 * * * * /home/ubuntu/doctor-ai-agent/deploy/tencent/auto_deploy_on_drift.sh \
#     >> /home/ubuntu/doctor-ai-agent/logs/auto_deploy.log 2>&1
set -euo pipefail

APP_DIR="/home/ubuntu/doctor-ai-agent"
LOCK="/tmp/auto_deploy_on_drift.lock"
MIN_AGE_SEC=300       # don't deploy a commit younger than 5 min
MAX_AGE_SEC=86400     # don't auto-deploy a commit older than 24h (suspicious)

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Single-instance via flock; if a previous run is still going, drop silently.
exec 9>"$LOCK"
if ! flock -xn 9; then
  exit 0
fi

cd "$APP_DIR"

git fetch gitee main --quiet || { echo "$(ts) WARN: git fetch failed"; exit 0; }

GITEE_SHA=$(git rev-parse gitee/main)
PROD_SHA=$(git rev-parse HEAD)
if [[ "$GITEE_SHA" == "$PROD_SHA" ]]; then
  exit 0  # in sync — common case
fi

COMMIT_TS=$(git show -s --format=%ct gitee/main)
NOW_TS=$(date +%s)
AGE_SEC=$(( NOW_TS - COMMIT_TS ))

if (( AGE_SEC < MIN_AGE_SEC )); then
  echo "$(ts) drift ${GITEE_SHA:0:7} but commit only $((AGE_SEC/60))m old; deferring"
  exit 0
fi
if (( AGE_SEC > MAX_AGE_SEC )); then
  echo "$(ts) WARN: drift > 24h (${GITEE_SHA:0:7}, $((AGE_SEC/3600))h old); skipping auto-deploy"
  exit 0
fi

echo "$(ts) drift detected: gitee/main=${GITEE_SHA:0:7} prod=${PROD_SHA:0:7}, age=$((AGE_SEC/60))m — running deploy.sh"
bash /home/ubuntu/deploy.sh
echo "$(ts) auto-deploy complete; prod now at $(git rev-parse HEAD | cut -c1-7)"
