#!/usr/bin/env bash
# install-vhosts.sh — link the four subdomain server blocks into
# /etc/nginx/sites-enabled and reload. Idempotent — safe to re-run.
#
# Source files live in deploy/tencent/nginx/. We don't copy them; we
# symlink so a future `git pull` updates the active config in place
# (matching the existing deploy.sh pattern of leaving deploy.sh as a
# symlink to /home/ubuntu/deploy.sh).
#
# Run as root on the Tencent host AFTER:
#   1. issue-wildcard-cert.sh has installed the cert.
#   2. /etc/nginx/htpasswd has at least one entry (htpasswd -c).
#   3. The four server_name DNS records resolve to this host.
#   4. You have replaced YOUR.HOME.IP / YOUR.OFFICE.IP placeholders in
#      deploy/tencent/nginx/ops.doctoragentai.cn.conf (and reviewed
#      phase0-lockdown.conf if you used it).

set -euo pipefail

REPO=/home/ubuntu/doctor-ai-agent
SRC="$REPO/deploy/tencent/nginx"
DST=/etc/nginx/sites-enabled

if grep -q YOUR.HOME.IP "$SRC/ops.doctoragentai.cn.conf"; then
  echo "ERROR: ops.doctoragentai.cn.conf still has YOUR.HOME.IP placeholder." >&2
  echo "Edit the file (commit + redeploy, or sed-replace in place) before running." >&2
  exit 1
fi

if [[ ! -s /etc/nginx/htpasswd ]]; then
  echo "ERROR: /etc/nginx/htpasswd is empty or missing." >&2
  echo "Create it first:  sudo htpasswd -c /etc/nginx/htpasswd opsuser" >&2
  exit 1
fi

if [[ ! -s /etc/nginx/certs/wildcard.doctoragentai.cn.crt ]]; then
  echo "ERROR: wildcard cert not found at /etc/nginx/certs/." >&2
  echo "Run issue-wildcard-cert.sh first." >&2
  exit 1
fi

for host in api app wiki ops; do
  src="$SRC/${host}.doctoragentai.cn.conf"
  link="$DST/${host}.doctoragentai.cn.conf"
  ln -sfn "$src" "$link"
  echo "linked $link -> $src"
done

# Sanity-check before reload.
nginx -t

# Use reload, not restart — keeps existing connections.
systemctl reload nginx
echo "OK: nginx reloaded with split vhosts."
echo
echo "Verify:"
echo "  curl -sI https://api.doctoragentai.cn/healthz   # expect 200"
echo "  curl -sI https://app.doctoragentai.cn/          # expect 200"
echo "  curl -sI https://wiki.doctoragentai.cn/         # expect 200"
echo "  curl -sI https://ops.doctoragentai.cn/          # expect 401 (auth required)"
