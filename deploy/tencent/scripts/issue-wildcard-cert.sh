#!/usr/bin/env bash
# issue-wildcard-cert.sh — provision and renew the *.doctoragentai.cn
# Let's Encrypt wildcard cert via DNS-01 against Tencent DNSPod.
#
# Why DNS-01 (not HTTP-01): wildcards REQUIRE DNS-01 per ACME spec.
# Why acme.sh (not certbot): native dnspod plugin, single binary, no
# python deps to keep current.
#
# Run as root on the Tencent host. Idempotent — re-running renews if
# the cert is within 30 days of expiry, else exits 0.
#
# Prereqs (one-time):
#   1. Tencent DNSPod API token: console → account → API keys.
#      Export DP_Id and DP_Key BEFORE running this script the first
#      time. acme.sh stores them in ~/.acme.sh/account.conf afterwards.
#   2. acme.sh installed: `curl https://get.acme.sh | sh -s email=YOU@DOMAIN`
#   3. DNS records for app/api/wiki/ops point at this host (Phase 2).

set -euo pipefail

CERT_DIR=/etc/nginx/certs
DOMAIN=doctoragentai.cn
ACME_HOME=${ACME_HOME:-$HOME/.acme.sh}

if [[ -z "${DP_Id:-}" || -z "${DP_Key:-}" ]]; then
  if ! grep -q '^SAVED_DP_Id=' "$ACME_HOME/account.conf" 2>/dev/null; then
    echo "ERROR: DP_Id and DP_Key must be exported the first time." >&2
    echo "  export DP_Id=<dnspod-api-id>" >&2
    echo "  export DP_Key=<dnspod-api-token>" >&2
    echo "Get them from https://console.dnspod.cn/account/token/apikey" >&2
    exit 1
  fi
fi

mkdir -p "$CERT_DIR"

# Issue the wildcard. acme.sh handles "already valid" → no-op on re-run.
"$ACME_HOME/acme.sh" --issue --dns dns_dp \
  -d "$DOMAIN" \
  -d "*.$DOMAIN" \
  --keylength 2048 \
  --server letsencrypt

# Install into nginx's cert dir with a reload hook.
"$ACME_HOME/acme.sh" --install-cert -d "$DOMAIN" \
  --key-file       "$CERT_DIR/wildcard.${DOMAIN}.key" \
  --fullchain-file "$CERT_DIR/wildcard.${DOMAIN}.crt" \
  --reloadcmd      "nginx -t && systemctl reload nginx"

echo "OK: wildcard cert installed at $CERT_DIR/wildcard.${DOMAIN}.{crt,key}"
echo "Renewal: acme.sh registers a daily cron in /etc/cron.d/ — verify with"
echo "  crontab -l | grep acme.sh"
