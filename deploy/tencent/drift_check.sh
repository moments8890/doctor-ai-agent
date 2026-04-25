#!/usr/bin/env bash
# drift_check.sh — daily prod deploy drift alarm
#
# Detects when the gitee→webhook→deploy.sh pipeline silently breaks.
# Compares gitee/main HEAD to the deployed HEAD on this host. If they
# diverge for more than THRESHOLD_MIN minutes, sends a GlitchTip event
# so the issue surfaces in the same dashboard as backend errors.
#
# Also pre-checks webhook listener health — catches cases where the
# listener died but no push has happened yet to expose it.
#
# Wire-up:
#   crontab -e (as ubuntu)
#   7 9 * * * /home/ubuntu/doctor-ai-agent/deploy/tencent/drift_check.sh \
#     >> /home/ubuntu/doctor-ai-agent/logs/drift_check.log 2>&1
set -euo pipefail

APP_DIR="/home/ubuntu/doctor-ai-agent"
THRESHOLD_MIN=10
SENTRY_DSN="https://111de78357f04cdbbe9b1400c06815b8@ops.doctoragentai.cn/glitchtip/1"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
notify() {
  local msg="$1"
  echo "$(ts) ALERT: $msg"
  SENTRY_DSN="$SENTRY_DSN" "$APP_DIR/.venv/bin/python" - "$msg" <<'PY'
import os, sys, sentry_sdk
sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0)
with sentry_sdk.push_scope() as scope:
    scope.set_tag("alert_kind", "deploy_drift")
    sentry_sdk.capture_message(f"[deploy-drift] {sys.argv[1]}", level="error")
sentry_sdk.flush(timeout=5)
PY
}

cd "$APP_DIR"
echo "$(ts) drift_check start"

# 1. Webhook listener health
if ! systemctl is-active --quiet doctor-ai-webhook.service; then
  notify "doctor-ai-webhook.service is not active — auto-deploy is down"
  exit 0
fi

# 2. Listener actually accepting connections (expect 401 for bad token)
probe_code=$(curl -s -o /dev/null -m 5 -w '%{http_code}' \
  -X POST -H 'X-Gitee-Token: drift-probe' -H 'Content-Type: application/json' \
  -d '{}' http://127.0.0.1:9000/hooks/deploy || echo "000")
if [[ "$probe_code" != "401" ]]; then
  notify "webhook port 9000 returned HTTP $probe_code (expected 401) — listener broken"
  exit 0
fi

# 3. SHA drift
git fetch gitee main --quiet
GITEE_SHA=$(git rev-parse gitee/main)
PROD_SHA=$(git rev-parse HEAD)
if [[ "$GITEE_SHA" == "$PROD_SHA" ]]; then
  echo "$(ts) OK: in sync at ${PROD_SHA:0:7}"
  exit 0
fi

COMMIT_TS=$(git show -s --format=%ct gitee/main)
NOW_TS=$(date +%s)
AGE_MIN=$(( (NOW_TS - COMMIT_TS) / 60 ))
if (( AGE_MIN < THRESHOLD_MIN )); then
  echo "$(ts) recent push (${AGE_MIN}m old) — skipping, deploy may be in flight"
  exit 0
fi

notify "gitee/main ${GITEE_SHA:0:7} not deployed (${AGE_MIN}m old; prod at ${PROD_SHA:0:7})"
