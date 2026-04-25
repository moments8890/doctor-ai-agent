#!/usr/bin/env bash
# mac_pull_backups.sh — runs ON THE MAC (not on Tencent). Pulls both
# backup chains down to /Volumes/ORICO/Code/db-backup/ for offline
# long-term storage.
#
# Two parallel sources, kept separate so we can tell them apart in
# recovery scenarios:
#   encrypted/  ← /home/ubuntu/backups/*.sql.gz.gpg (GPG private key
#                 lives only on this Mac → nothing on prod can decrypt)
#   cos/        ← cos://doctor-ai-backups-1408751198/mysql-daily/*.sql.gz
#                 (plaintext, but private bucket; faster recovery)
#
# Mac-side retention: forever. Storage is cheap on the ORICO drive,
# and the whole point of pulling is offline cold storage.
#
# Wire-up via launchd:
#   ~/Library/LaunchAgents/com.doctoragentai.pull-backups.plist
#   (created alongside this script)
set -euo pipefail

DEST="/Volumes/ORICO/Code/db-backup"
SSH_HOST="tencent"
COS_BUCKET="doctor-ai-backups-1408751198"
COS_REGION="ap-shanghai"
LOG="$DEST/logs/pull-$(date +%Y-%m).log"

mkdir -p "$DEST/encrypted" "$DEST/cos" "$DEST/logs"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

log() { echo "$(ts) $*" | tee -a "$LOG"; }

log "=== pull start ==="

# 1. Bail early if ORICO drive isn't mounted (don't spam errors)
if [[ ! -d "/Volumes/ORICO" ]]; then
  echo "$(ts) ORICO drive not mounted — skipping pull" >&2
  exit 0
fi

# 2. Encrypted chain: rsync over SSH, additive (don't delete remote files)
log "syncing encrypted backups from $SSH_HOST:/home/ubuntu/backups/ ..."
rsync -av --include='*.sql.gz.gpg' --include='*.sql.gz' --include='*.sql' \
      --exclude='*' \
      "$SSH_HOST:/home/ubuntu/backups/" "$DEST/encrypted/" \
      2>&1 | tee -a "$LOG"
encrypted_count=$(ls -1 "$DEST/encrypted/" 2>/dev/null | wc -l | tr -d ' ')
log "encrypted/: $encrypted_count file(s) total"

# 3. COS chain: pull anything new via Python SDK
TCCLI_CRED="$HOME/.tccli/credential"
# Use the pipx-tccli venv's python — the system python doesn't have qcloud_cos.
# Install with:  pipx inject tccli cos-python-sdk-v5
PIPX_PYTHON="$HOME/.local/pipx/venvs/tccli/bin/python"
if [[ -f "$TCCLI_CRED" && -x "$PIPX_PYTHON" ]]; then
  log "syncing COS backups from cos://$COS_BUCKET/mysql-daily/ ..."
  "$PIPX_PYTHON" - <<PY 2>&1 | tee -a "$LOG"
import configparser, os, sys
try:
    from qcloud_cos import CosConfig, CosS3Client
except ImportError:
    print(f"{__import__('datetime').datetime.utcnow().isoformat()}Z WARN: qcloud_cos not installed locally — skip COS pull. Install with: pipx inject tccli cos-python-sdk-v5  (or pip install --user)")
    sys.exit(0)
cp = configparser.ConfigParser()
cp.read("$TCCLI_CRED")
client = CosS3Client(CosConfig(
    Region="$COS_REGION",
    SecretId=cp.get("default", "secretId"),
    SecretKey=cp.get("default", "secretKey"),
))
resp = client.list_objects(Bucket="$COS_BUCKET", Prefix="mysql-daily/")
new_count = 0
for obj in resp.get("Contents", []):
    key = obj["Key"]
    local = os.path.join("$DEST/cos", os.path.basename(key))
    if os.path.exists(local) and os.path.getsize(local) == int(obj["Size"]):
        continue
    print(f"  pulling {key} ({int(obj['Size']):,}B)")
    client.download_file(Bucket="$COS_BUCKET", Key=key, DestFilePath=local)
    new_count += 1
print(f"  COS pulled: {new_count} new file(s)")
PY
else
  log "WARN: missing $TCCLI_CRED or $PIPX_PYTHON — skip COS pull"
fi

cos_count=$(ls -1 "$DEST/cos/" 2>/dev/null | wc -l | tr -d ' ')
log "cos/: $cos_count file(s) total"

# 4. Disk usage sanity
total_size=$(du -sh "$DEST" 2>/dev/null | awk '{print $1}')
log "=== pull done — total local size: $total_size ==="
