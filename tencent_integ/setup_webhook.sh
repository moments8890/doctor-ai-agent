#!/usr/bin/env bash
# Run this ONCE on the Tencent VM to install the webhook auto-deploy pipeline.
# Usage:  bash setup_webhook.sh <webhook-secret>
set -euo pipefail

SECRET="${1:?Usage: $0 <webhook-secret>}"
APP_DIR="/home/ubuntu/doctor-ai-agent"
SERVICE_SRC="$APP_DIR/tencent_integ/doctor-ai-webhook.service"
DEPLOY_SRC="$APP_DIR/tencent_integ/deploy.sh"

echo "--- 1. writing /home/ubuntu/.webhook.env"
cat > /home/ubuntu/.webhook.env <<EOF
WEBHOOK_SECRET=${SECRET}
WEBHOOK_PORT=9000
DEPLOY_SCRIPT=/home/ubuntu/deploy.sh
EOF
chmod 600 /home/ubuntu/.webhook.env

echo "--- 2. copying deploy.sh"
cp "$DEPLOY_SRC" /home/ubuntu/deploy.sh
chmod +x /home/ubuntu/deploy.sh

echo "--- 3. sudoers entry for passwordless restart"
SUDOERS_LINE="ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart doctor-ai-backend"
SUDOERS_FILE="/etc/sudoers.d/doctor-ai-deploy"
echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE" > /dev/null
sudo chmod 0440 "$SUDOERS_FILE"
# Validate
sudo visudo -cf "$SUDOERS_FILE"

echo "--- 4. installing systemd service"
sudo cp "$SERVICE_SRC" /etc/systemd/system/doctor-ai-webhook.service
sudo systemctl daemon-reload
sudo systemctl enable doctor-ai-webhook
sudo systemctl restart doctor-ai-webhook
sudo systemctl status doctor-ai-webhook --no-pager

echo "--- 5. open port 9000 in local firewall (if ufw active)"
if sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 9000/tcp comment "Gitee webhook"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Webhook URL to register in Gitee:"
echo "  http://101.35.116.122:9000/hooks/deploy"
echo ""
echo "Also open TCP 9000 in Tencent Cloud Security Group if not already done."
