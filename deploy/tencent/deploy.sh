#!/usr/bin/env bash
# deploy.sh — 自动部署脚本
#
# 用途：从 Gitee 拉取最新代码，同步 Python 依赖，重启后端服务。
# 触发方式：由 webhook_server.py 在收到 Gitee push 事件后调用，也可手动执行。
# 幂等性：可重复运行，webhook_server 持有锁防止并发重入。
# 日志输出至：$APP_DIR/logs/deploy.log
set -euo pipefail

APP_DIR="/home/ubuntu/doctor-ai-agent"
SERVICE="doctor-ai-backend"
VENV="$APP_DIR/.venv"
LOG="$APP_DIR/logs/deploy.log"

exec >> "$LOG" 2>&1
echo "=== deploy started at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

cd "$APP_DIR"

# Ensure gitee remote exists
if ! git remote get-url gitee &>/dev/null; then
    git remote add gitee git@gitee.com:moments6674/doctor-ai-agent.git
fi

# Pull latest from Gitee
git fetch gitee
git reset --hard gitee/main

# Sync Python dependencies
"$VENV/bin/pip" install -q -r requirements.txt

# Restart backend via systemd
sudo systemctl restart "$SERVICE"

echo "=== deploy finished at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
