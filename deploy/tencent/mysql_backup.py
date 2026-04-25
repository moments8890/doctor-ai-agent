#!/home/ubuntu/doctor-ai-agent/.venv/bin/python
"""mysql_backup.py — daily MySQL → Tencent COS backup.

Why: the doctor-ai MySQL container runs on a single CVM with a single
disk and no replicas. If the disk fails or the VM is deleted, every
doctor's rules and patient record is gone forever. This script ships
a compressed mysqldump to COS every day so the data survives even
total host loss.

How:
  1. `docker exec` mysqldump on the running doctor-ai-mysql container,
     using the container's own MYSQL_ROOT_PASSWORD env (no creds in
     this script or its config).
  2. Pipe through gzip locally.
  3. Upload to cos://doctor-ai-backups-1408751198/mysql-daily/<date>.sql.gz
     with a lifecycle policy that auto-deletes after 90 days.
  4. Verify size matches before declaring success.
  5. Post a heartbeat (success or failure) to GlitchTip with tag
     alert_kind=mysql_backup so missing backups surface in the same
     dashboard as deploy drift.

Wire-up (host crontab):
  17 3 * * * /home/ubuntu/doctor-ai-agent/deploy/tencent/mysql_backup.py \
    >> /home/ubuntu/doctor-ai-agent/logs/mysql_backup.log 2>&1

Restore: see deploy/tencent/mysql_restore.md
"""
from __future__ import annotations

import datetime as dt
import gzip
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

import sentry_sdk
from qcloud_cos import CosConfig, CosS3Client

# ---- Config ----------------------------------------------------------------

BUCKET = "doctor-ai-backups-1408751198"
REGION = "ap-shanghai"
PREFIX = "mysql-daily"
CONTAINER = "doctor-ai-mysql"
SENTRY_DSN = "https://111de78357f04cdbbe9b1400c06815b8@ops.doctoragentai.cn/glitchtip/1"

# Tencent CAM creds — same key tccli uses. Read from env if set, else
# fall back to ~/.tccli/credential. Never write to disk inside this
# script's directory.
SECRET_ID = os.environ.get("TENCENTCLOUD_SECRET_ID")
SECRET_KEY = os.environ.get("TENCENTCLOUD_SECRET_KEY")
if not (SECRET_ID and SECRET_KEY):
    import configparser
    cp = configparser.ConfigParser()
    cp.read(os.path.expanduser("~/.tccli/credential"))
    SECRET_ID = cp.get("default", "secretId", fallback=None)
    SECRET_KEY = cp.get("default", "secretKey", fallback=None)
if not (SECRET_ID and SECRET_KEY):
    print("FATAL: no Tencent credentials (env or ~/.tccli/credential)", file=sys.stderr)
    sys.exit(2)


def ts() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def heartbeat(level: str, msg: str, **extras) -> None:
    """Post the backup result to GlitchTip so missing runs are visible."""
    try:
        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0)
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("alert_kind", "mysql_backup")
            for k, v in extras.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(msg, level=level)
        sentry_sdk.flush(timeout=5)
    except Exception as e:
        print(f"{ts()} heartbeat failed: {e}", file=sys.stderr)


def dump_to(path: str) -> int:
    """Run mysqldump inside the container, gzip locally, return byte size."""
    cmd = [
        "sudo", "docker", "exec", CONTAINER,
        "sh", "-c",
        # --single-transaction: consistent snapshot without locking the whole DB
        # --routines + --triggers: include stored procedures & triggers
        # --no-tablespaces: avoids needing PROCESS privilege in MySQL 8
        # --all-databases: includes mysql.user etc. so a full restore works
        'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" '
        '--single-transaction --quick --no-tablespaces '
        '--routines --triggers --all-databases',
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with gzip.open(path, "wb") as gz:
        shutil.copyfileobj(proc.stdout, gz)
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"mysqldump exit {proc.returncode}: {err.decode(errors='replace')[:500]}")
    return os.path.getsize(path)


def upload(local_path: str, key: str, cos_client: CosS3Client) -> None:
    cos_client.upload_file(
        Bucket=BUCKET,
        LocalFilePath=local_path,
        Key=key,
        # Multipart for files > 10MB (will basically never trigger for
        # this DB but cheap insurance for the future).
        MAXThread=4,
        EnableMD5=True,
    )


def ensure_lifecycle(cos_client: CosS3Client) -> None:
    """Apply a 90-day expiry rule to the mysql-daily/ prefix.

    Idempotent — replaces any existing lifecycle config. Cheap to call
    every run, keeps the policy authoritatively defined here.
    """
    config = {
        "Rule": [
            {
                "ID": "expire-mysql-daily-after-90d",
                "Status": "Enabled",
                "Filter": {"Prefix": f"{PREFIX}/"},
                "Expiration": {"Days": "90"},
            }
        ]
    }
    cos_client.put_bucket_lifecycle(Bucket=BUCKET, LifecycleConfiguration=config)


def main() -> int:
    started = dt.datetime.utcnow()
    date_tag = started.strftime("%Y%m%d_%H%M%S")
    key = f"{PREFIX}/doctor_ai_{date_tag}.sql.gz"

    print(f"{ts()} starting MySQL backup → cos://{BUCKET}/{key}")

    cos_client = CosS3Client(CosConfig(
        Region=REGION, SecretId=SECRET_ID, SecretKey=SECRET_KEY,
    ))

    try:
        ensure_lifecycle(cos_client)
    except Exception as e:
        # Non-fatal — the backup itself is more important than the policy.
        print(f"{ts()} WARN: lifecycle policy update failed: {e}")

    with tempfile.NamedTemporaryFile(suffix=".sql.gz", delete=False) as tf:
        tmp_path = tf.name

    try:
        size = dump_to(tmp_path)
        print(f"{ts()} dump complete: {size:,} bytes")

        if size < 1024:
            raise RuntimeError(f"dump suspiciously small ({size} bytes) — likely empty/error")

        upload(tmp_path, key, cos_client)
        print(f"{ts()} upload OK: cos://{BUCKET}/{key}")

        # Verify by HEAD
        head = cos_client.head_object(Bucket=BUCKET, Key=key)
        remote_size = int(head.get("Content-Length", 0))
        if remote_size != size:
            raise RuntimeError(f"size mismatch: local={size} remote={remote_size}")

        elapsed = (dt.datetime.utcnow() - started).total_seconds()
        msg = f"[mysql-backup] OK {size:,}B in {elapsed:.1f}s → {key}"
        print(f"{ts()} {msg}")
        heartbeat("info", msg, size_bytes=size, key=key, duration_sec=elapsed)
        return 0

    except Exception as e:
        tb = traceback.format_exc()
        msg = f"[mysql-backup] FAILED: {type(e).__name__}: {e}"
        print(f"{ts()} {msg}\n{tb}", file=sys.stderr)
        heartbeat("error", msg, traceback=tb[-2000:])
        return 1

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
