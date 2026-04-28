#!/usr/bin/env python3
"""
webhook_server.py — Gitee Webhook 监听服务

监听端口：9000（由 nginx 代理 /hooks/deploy → 127.0.0.1:9000）
分发规则：根据 push payload 的 ref 字段选择对应分支的 deploy 脚本
并发保护：每个分支独立持有一把锁；同分支重复请求跳过；不同分支请求并行。

Python 3.9 compatible per AGENTS.md:120 — no `list[str]` / `str | None`,
typing imports only.
"""
from __future__ import annotations

import hmac
import http.server
import json
import logging
import os
import subprocess
import threading
from typing import Dict, List, Optional

PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
SECRET = os.environ.get("WEBHOOK_SECRET", "")

# Branch → deploy command. The staging command runs under a systemd slice so
# its RAM/CPU is capped and cannot starve prod. Slice unit lives at
# /etc/systemd/system/staging-build.slice (see Task 8).
BRANCH_DEPLOYS: Dict[str, List[str]] = {
    "main": [
        "/bin/bash",
        os.environ.get("DEPLOY_SCRIPT_MAIN", "/home/ubuntu/deploy.sh"),
    ],
    # systemd-run prefixed with sudo: webhook runs as `ubuntu`, but
    # `--slice=staging-build.slice` is a system slice (not a user slice),
    # which only attaches when systemd-run is invoked as root. The matching
    # NOPASSWD sudoers entry is in /etc/sudoers.d/doctor-ai-deploy
    # (DOCTORAI_STAGING_RUN alias).
    "staging": [
        "/usr/bin/sudo",
        "/usr/bin/systemd-run",
        "--unit=staging-deploy-%s" % os.getpid(),
        "--slice=staging-build.slice",
        "--collect",
        "--wait",
        "--quiet",
        "/bin/bash",
        os.environ.get("DEPLOY_SCRIPT_STAGING", "/home/ubuntu/deploy-staging.sh"),
    ],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("webhook")

# One lock per branch — main and staging deploys can run concurrently;
# two pushes to the same branch within one deploy window queue (skip).
_locks: Dict[str, threading.Lock] = {b: threading.Lock() for b in BRANCH_DEPLOYS}


def _run_deploy(branch: str, command: List[str]) -> None:
    lock = _locks[branch]
    if not lock.acquire(blocking=False):
        log.warning("deploy already in progress for %s — skipping", branch)
        return
    try:
        log.info("starting %s deploy: %s", branch, " ".join(command))
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=900,  # 15 min — npm ci on cold cache ~3 min, plus headroom
        )
        if result.returncode == 0:
            log.info("%s deploy succeeded:\n%s", branch, result.stdout[-2000:])
        else:
            log.error(
                "%s deploy failed (rc=%d):\n%s\n%s",
                branch,
                result.returncode,
                result.stdout[-1000:],
                result.stderr[-1000:],
            )
    except subprocess.TimeoutExpired:
        log.error("%s deploy timed out after 15 min", branch)
    except Exception as exc:
        log.exception("%s deploy error: %s", branch, exc)
    finally:
        lock.release()


def _branch_from_ref(ref: str) -> Optional[str]:
    # gitee sends e.g. "refs/heads/main" or "refs/heads/staging"
    prefix = "refs/heads/"
    if ref.startswith(prefix):
        return ref[len(prefix):]
    return None


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        if self.path not in ("/hooks/deploy", "/hooks/deploy/"):
            self._reply(404, "not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        token = self.headers.get("X-Gitee-Token", "")
        if SECRET and not hmac.compare_digest(token, SECRET):
            log.warning("invalid token from %s", self.client_address[0])
            self._reply(401, "unauthorized")
            return

        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}

        ref = payload.get("ref", "")
        branch = _branch_from_ref(ref)
        log.info("push event ref=%r (branch=%r) from %s", ref, branch, self.client_address[0])

        command = BRANCH_DEPLOYS.get(branch) if branch else None
        if not command:
            log.info("ignoring push to unknown branch %r", branch)
            self._reply(200, "ignored: unknown branch")
            return

        threading.Thread(
            target=_run_deploy, args=(branch, command), daemon=True
        ).start()
        self._reply(200, f"deploying {branch}")

    def _reply(self, code: int, msg: str):
        body = (msg + "\n").encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if not SECRET:
        log.warning("WEBHOOK_SECRET is not set — all requests will be accepted")
    BIND = os.environ.get("WEBHOOK_BIND", "127.0.0.1")
    server = http.server.ThreadingHTTPServer((BIND, PORT), WebhookHandler)
    log.info("webhook server listening on %s:%d (branches: %s)",
             BIND, PORT, ", ".join(BRANCH_DEPLOYS.keys()))
    server.serve_forever()
