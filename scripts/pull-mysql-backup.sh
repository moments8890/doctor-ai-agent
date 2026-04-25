#!/usr/bin/env bash
# pull-mysql-backup.sh — pull the latest encrypted prod-MySQL backups from
# tencent → local Mac mini.
#
# Runs from cron daily at ~04:30 UTC (15 min after the prod backup script
# fires at 04:15). rsync is incremental, so re-runs are cheap and missed
# pulls catch up automatically.
#
# Encrypted at rest with the GPG public key in /home/ubuntu/.gnupg-backup
# on prod; the private half lives only on this Mac mini at
# ~/.gnupg/doctor-ai-backup. Restore with:
#   GNUPGHOME=~/.gnupg/doctor-ai-backup gpg --decrypt \
#     ~/doctor-ai-backups/doctor_ai_<TS>.sql.gz.gpg | gunzip > restore.sql
#
# Wire-up:
#   crontab -e
#   30 4 * * * /Volumes/ORICO/Code/doctor-ai-agent/scripts/pull-mysql-backup.sh \
#     >> $HOME/doctor-ai-backups/pull.log 2>&1
set -euo pipefail

LOCAL_DIR="$HOME/doctor-ai-backups"
SSH_HOST="tencent"
REMOTE_DIR="/home/ubuntu/backups/"
RETENTION_DAYS=365

mkdir -p "$LOCAL_DIR"
echo "$(date -u +%FT%TZ) pull start"

# rsync only the encrypted backups (not older plaintext .sql.gz files).
# Plain `-az` for compatibility with macOS's openrsync, which doesn't
# accept --info=stats1.
rsync -az \
  --include='doctor_ai_*.sql.gz.gpg' --exclude='*' \
  "$SSH_HOST:$REMOTE_DIR" "$LOCAL_DIR/"

# Local retention prune (1 year of dailies).
find "$LOCAL_DIR" -name 'doctor_ai_*.sql.gz.gpg' -mtime "+$RETENTION_DAYS" -print -delete \
  | sed "s|^|$(date -u +%FT%TZ) pruned: |"

LATEST=$(ls -t "$LOCAL_DIR"/doctor_ai_*.sql.gz.gpg 2>/dev/null | head -1)
if [[ -n "$LATEST" ]]; then
  AGE_HRS=$(( ($(date +%s) - $(stat -f %m "$LATEST")) / 3600 ))
  echo "$(date -u +%FT%TZ) latest=$LATEST age=${AGE_HRS}h"
  if (( AGE_HRS > 36 )); then
    echo "$(date -u +%FT%TZ) WARN: latest backup is older than 36h — investigate"
  fi
fi
