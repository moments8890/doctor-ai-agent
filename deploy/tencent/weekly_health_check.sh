#!/usr/bin/env bash
# weekly_health_check.sh — broad infrastructure sanity sweep
#
# Catches creeping issues that the daily drift_check.sh does NOT see:
#   - CVM/cert/domain expirations
#   - Disk usage trending up
#   - Services that are "running" but actually broken
#   - Docker stack drift
#   - SES quota / template approval status changes
#
# Posts a summary event to GlitchTip with tag alert_kind=weekly_health
# (separate from deploy_drift). Once SES template 174869 is approved,
# upgrade this to also send an email digest.
#
# Wire-up:
#   crontab -e (as ubuntu)
#   13 9 * * 1 /home/ubuntu/doctor-ai-agent/deploy/tencent/weekly_health_check.sh \
#     >> /home/ubuntu/doctor-ai-agent/logs/weekly_health.log 2>&1
set -uo pipefail  # no -e — we want all checks to run even if one fails

APP_DIR="/home/ubuntu/doctor-ai-agent"
SENTRY_DSN="https://111de78357f04cdbbe9b1400c06815b8@api.doctoragentai.cn/glitchtip/1"
TCCLI="$HOME/.local/bin/tccli"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "$(ts) weekly_health_check start"

issues=()

# 1. Disk usage
disk_pct=$(df / | awk 'NR==2 {gsub("%",""); print $5}')
if (( disk_pct >= 85 )); then
  issues+=("DISK: / at ${disk_pct}% (>= 85%)")
fi

# 2. SSL cert expiry (api.doctoragentai.cn)
cert_path="/etc/letsencrypt/live/api.doctoragentai.cn/fullchain.pem"
if [[ -f "$cert_path" ]]; then
  expiry=$(sudo openssl x509 -in "$cert_path" -noout -enddate 2>/dev/null | cut -d= -f2)
  expiry_epoch=$(date -d "$expiry" +%s 2>/dev/null || echo 0)
  now_epoch=$(date +%s)
  days_left=$(( (expiry_epoch - now_epoch) / 86400 ))
  if (( days_left < 30 )); then
    issues+=("SSL: api.doctoragentai.cn cert expires in ${days_left}d (${expiry})")
  fi
fi

# 3. Critical systemd services
for svc in doctor-ai-backend doctor-ai-webhook nginx; do
  if ! systemctl is-active --quiet "$svc"; then
    issues+=("SERVICE: $svc not active")
  fi
done

# 4. Docker stack
expected_containers=("glitchtip-web-1" "glitchtip-worker-1" "glitchtip-postgres-1" "glitchtip-redis-1" "doctor-ai-mysql")
running=$(sudo docker ps --format '{{.Names}}')
for c in "${expected_containers[@]}"; do
  if ! grep -qx "$c" <<<"$running"; then
    issues+=("DOCKER: container $c not running")
  fi
done

# 5. Backend health
if ! curl -fsS --max-time 5 http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
  issues+=("BACKEND: /healthz did not return 2xx")
fi

# 6. Gitee ↔ prod sync (mostly redundant with drift_check.sh, but cheap)
cd "$APP_DIR"
git fetch gitee main --quiet 2>/dev/null
gitee_sha=$(git rev-parse gitee/main 2>/dev/null)
prod_sha=$(git rev-parse HEAD 2>/dev/null)
if [[ -n "$gitee_sha" && "$gitee_sha" != "$prod_sha" ]]; then
  commit_ts=$(git show -s --format=%ct gitee/main)
  age_min=$(( ( $(date +%s) - commit_ts ) / 60 ))
  if (( age_min > 60 )); then
    issues+=("DRIFT: gitee/main ${gitee_sha:0:7} not deployed (${age_min}m old)")
  fi
fi

# 7. CVM expiration (via tccli — only if creds present)
if [[ -x "$TCCLI" && -f "$HOME/.tccli/credential" ]]; then
  expiry_iso=$("$TCCLI" cvm DescribeInstances --region ap-shanghai 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['InstanceSet'][0]['ExpiredTime'] if d['InstanceSet'] else '')" 2>/dev/null)
  if [[ -n "$expiry_iso" ]]; then
    expiry_epoch=$(date -d "$expiry_iso" +%s 2>/dev/null || echo 0)
    days_left=$(( (expiry_epoch - $(date +%s)) / 86400 ))
    if (( days_left < 30 )); then
      issues+=("CVM: doctor-ai-prod-cvm-01 expires in ${days_left}d (${expiry_iso})")
    fi
  fi

  # 8. SES template status — if 174869 just approved, that's good news worth surfacing
  status=$("$TCCLI" ses ListEmailTemplates --region ap-hongkong --Offset 0 --Limit 10 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); m=[t for t in d.get('TemplatesMetadata',[]) if t.get('TemplateID')==174869]; print(m[0]['TemplateStatus'] if m else '')" 2>/dev/null)
  if [[ "$status" == "0" ]]; then
    issues+=("SES: template 174869 (doctor_ai_system_alert) APPROVED — wire drift_check.sh to use it for email alerts")
  elif [[ "$status" == "2" ]]; then
    issues+=("SES: template 174869 REJECTED — check ReviewReason and resubmit")
  fi
fi

# Report
if (( ${#issues[@]} == 0 )); then
  echo "$(ts) all checks passed (disk=${disk_pct}%, services=ok, sync=ok)"
  exit 0
fi

echo "$(ts) FOUND ${#issues[@]} ISSUE(S):"
for i in "${issues[@]}"; do echo "  - $i"; done

# Post to GlitchTip
SENTRY_DSN="$SENTRY_DSN" "$APP_DIR/.venv/bin/python" - <<PY
import os, sentry_sdk
sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0)
issues = """$(printf '  - %s\n' "${issues[@]}")"""
with sentry_sdk.push_scope() as scope:
    scope.set_tag("alert_kind", "weekly_health")
    scope.set_extra("issue_count", ${#issues[@]})
    scope.set_extra("issues", issues)
    sentry_sdk.capture_message(
        f"[weekly-health] ${#issues[@]} issue(s) found:\n" + issues,
        level="warning",
    )
sentry_sdk.flush(timeout=5)
PY
