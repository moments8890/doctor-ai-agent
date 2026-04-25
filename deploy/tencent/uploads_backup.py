#!/home/ubuntu/doctor-ai-agent/.venv/bin/python
"""uploads_backup.py — incremental sync of doctor-uploaded files to COS.

The /home/ubuntu/doctor-ai-agent/uploads/ tree holds doctor-uploaded
KB documents (PDFs etc.) keyed by doctor ID. They were not in any
backup chain — disk loss = permanent loss of every doctor's KB
attachments.

This script does an additive sync: every file in the local tree is
mirrored to cos://doctor-ai-backups-1408751198/uploads/<same-path>.
Files already present (matched by size) are skipped — so daily reruns
are nearly-free if nothing changed.

We don't delete from COS when local files disappear. The whole point
is to recover from local loss; mirroring deletions would defeat that.
Old / orphaned objects stay until manual cleanup or lifecycle policy
expiration.

Wire-up via host crontab:
  37 3 * * * /home/ubuntu/doctor-ai-agent/deploy/tencent/uploads_backup.py \
    >> /home/ubuntu/doctor-ai-agent/logs/uploads_backup.log 2>&1
"""
from __future__ import annotations

import configparser
import datetime as dt
import os
import sys
import traceback

import sentry_sdk
from qcloud_cos import CosConfig, CosS3Client

UPLOADS_DIR = "/home/ubuntu/doctor-ai-agent/uploads"
BUCKET = "doctor-ai-backups-1408751198"
REGION = "ap-shanghai"
PREFIX = "uploads"
SENTRY_DSN = "https://111de78357f04cdbbe9b1400c06815b8@ops.doctoragentai.cn/glitchtip/1"


def ts() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def heartbeat(level: str, msg: str, **extras) -> None:
    try:
        sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0)
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("alert_kind", "uploads_backup")
            for k, v in extras.items():
                scope.set_extra(k, v)
            sentry_sdk.capture_message(msg, level=level)
        sentry_sdk.flush(timeout=5)
    except Exception as e:
        print(f"{ts()} heartbeat failed: {e}", file=sys.stderr)


def get_remote_index(client: CosS3Client) -> dict[str, int]:
    """Return {key: size} for everything currently in cos://bucket/uploads/."""
    index: dict[str, int] = {}
    marker = ""
    while True:
        resp = client.list_objects(
            Bucket=BUCKET, Prefix=f"{PREFIX}/", Marker=marker, MaxKeys=1000,
        )
        for obj in resp.get("Contents", []):
            index[obj["Key"]] = int(obj["Size"])
        if resp.get("IsTruncated") in ("true", True):
            marker = resp.get("NextMarker", "")
            if not marker:
                break
        else:
            break
    return index


def main() -> int:
    started = dt.datetime.utcnow()
    print(f"{ts()} starting uploads sync → cos://{BUCKET}/{PREFIX}/")

    if not os.path.isdir(UPLOADS_DIR):
        print(f"{ts()} no uploads dir at {UPLOADS_DIR} — nothing to do")
        return 0

    cp = configparser.ConfigParser()
    cp.read(os.path.expanduser("~/.tccli/credential"))
    secret_id = cp.get("default", "secretId", fallback=None)
    secret_key = cp.get("default", "secretKey", fallback=None)
    if not (secret_id and secret_key):
        print("FATAL: no Tencent creds in ~/.tccli/credential", file=sys.stderr)
        return 2

    client = CosS3Client(CosConfig(
        Region=REGION, SecretId=secret_id, SecretKey=secret_key,
    ))

    try:
        remote = get_remote_index(client)
        local_count = 0
        local_bytes = 0
        uploaded = 0
        skipped = 0
        failed: list[str] = []

        for root, _dirs, files in os.walk(UPLOADS_DIR):
            for fn in files:
                local_path = os.path.join(root, fn)
                rel = os.path.relpath(local_path, UPLOADS_DIR)
                key = f"{PREFIX}/{rel}"
                size = os.path.getsize(local_path)
                local_count += 1
                local_bytes += size

                if remote.get(key) == size:
                    skipped += 1
                    continue

                try:
                    client.upload_file(
                        Bucket=BUCKET, LocalFilePath=local_path, Key=key,
                        EnableMD5=True,
                    )
                    uploaded += 1
                    print(f"{ts()}   ↑ {key} ({size:,}B)")
                except Exception as e:
                    failed.append(f"{key}: {e}")
                    print(f"{ts()}   ✗ {key}: {e}", file=sys.stderr)

        elapsed = (dt.datetime.utcnow() - started).total_seconds()
        msg = (f"[uploads-backup] {uploaded} uploaded / {skipped} skipped "
               f"({local_count} local files, {local_bytes:,}B) in {elapsed:.1f}s")
        print(f"{ts()} {msg}")

        if failed:
            heartbeat(
                "error",
                f"[uploads-backup] {len(failed)} upload(s) FAILED",
                failed_keys=failed[:20],  # cap at 20 for event size
                uploaded=uploaded,
                skipped=skipped,
            )
            return 1

        # Only heartbeat non-trivial runs — silence noise when nothing changed.
        if uploaded > 0:
            heartbeat("info", msg, uploaded=uploaded, skipped=skipped, bytes=local_bytes)
        return 0

    except Exception as e:
        tb = traceback.format_exc()
        msg = f"[uploads-backup] FAILED: {type(e).__name__}: {e}"
        print(f"{ts()} {msg}\n{tb}", file=sys.stderr)
        heartbeat("error", msg, traceback=tb[-2000:])
        return 1


if __name__ == "__main__":
    sys.exit(main())
