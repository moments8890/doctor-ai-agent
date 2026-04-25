#!/usr/bin/env bash
# backup_mysql.sh — daily encrypted backup of the prod MySQL DB.
#
# Pipeline:
#   docker exec mysqldump → gzip → gpg --encrypt (recipient: backup keypair)
#   → /home/ubuntu/backups/doctor_ai_<date>.sql.gz.gpg
#
# The encryption keypair is asymmetric: the public half lives on this host
# (in /home/ubuntu/.gnupg-backup), the private half lives only on the Mac
# mini that pulls these files. So a compromised prod host cannot decrypt
# yesterday's backup, only encrypt new ones.
#
# Local retention: 14 days (Mac mini keeps the long tail).
#
# Wire-up (already done on prod):
#   crontab -e (as ubuntu)
#   15 4 * * * /home/ubuntu/doctor-ai-agent/deploy/tencent/backup_mysql.sh \
#     >> /home/ubuntu/doctor-ai-agent/logs/backup.log 2>&1
set -euo pipefail

BACKUP_DIR="/home/ubuntu/backups"
GNUPGHOME="/home/ubuntu/.gnupg-backup"
RECIPIENT="backup@doctoragentai.cn"
DB_USER="doctor_ai"
DB_NAME="doctor_ai"
CONTAINER="doctor-ai-mysql"
RETENTION_DAYS=14

# Pull MySQL password from runtime.json so we don't duplicate it here.
# Avoid jq — not installed on prod by default. set +o pipefail around the
# extraction since grep/sed-no-match is normal flow control, not failure.
set +o pipefail
PW=$(grep -A1 '"DATABASE_URL"' /home/ubuntu/doctor-ai-agent/config/runtime.json \
     | sed -nE 's|.*://[^:]+:([^@]+)@.*|\1|p' | head -1)
set -o pipefail
[[ -n "$PW" ]] || { echo "$(date -u +%FT%TZ) ERR: cannot read DB password"; exit 1; }

mkdir -p "$BACKUP_DIR"
TS=$(date -u +%Y%m%d-%H%M%S)
OUT="$BACKUP_DIR/doctor_ai_${TS}.sql.gz.gpg"

echo "$(date -u +%FT%TZ) backup start → $OUT"

docker exec "$CONTAINER" mysqldump \
    -u "$DB_USER" -p"$PW" \
    --single-transaction --quick --no-tablespaces --routines --triggers \
    "$DB_NAME" 2>/dev/null \
  | gzip -9 \
  | GNUPGHOME="$GNUPGHOME" gpg --batch --yes --trust-model always \
        --encrypt --recipient "$RECIPIENT" \
        --output "$OUT"

SIZE=$(stat -c '%s' "$OUT")
echo "$(date -u +%FT%TZ) backup done | size=$SIZE bytes | path=$OUT"

# Local retention prune
find "$BACKUP_DIR" -name 'doctor_ai_*.sql.gz.gpg' -mtime "+$RETENTION_DAYS" -print -delete \
  | sed "s|^|$(date -u +%FT%TZ) pruned: |"
