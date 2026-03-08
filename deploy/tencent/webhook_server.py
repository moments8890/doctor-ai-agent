#!/usr/bin/env python3
"""
webhook_server.py — Gitee Webhook 监听服务

用途：监听来自 Gitee 的 push 事件，验证 X-Gitee-Token 后异步执行 deploy.sh。
运行方式：由 doctor-ai-webhook systemd 服务托管，读取 ~/.webhook.env 中的环境变量。
监听端口：9000（由 nginx 代理，对外路径为 /hooks/deploy）
并发保护：同一时刻只允许一个 deploy.sh 实例运行，重复请求直接跳过。

使用方法（手动测试）：
    WEBHOOK_SECRET=<your-secret> python3 webhook_server.py
"""
import hashlib
import hmac
import http.server
import json
import logging
import os
import subprocess
import threading

PORT = int(os.environ.get("WEBHOOK_PORT", "9000"))
SECRET = os.environ.get("WEBHOOK_SECRET", "")
DEPLOY_SCRIPT = os.environ.get("DEPLOY_SCRIPT", "/home/ubuntu/deploy.sh")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("webhook")

_deploy_lock = threading.Lock()


def _run_deploy():
    if not _deploy_lock.acquire(blocking=False):
        log.warning("deploy already in progress — skipping")
        return
    try:
        log.info("starting deploy: %s", DEPLOY_SCRIPT)
        result = subprocess.run(
            ["/bin/bash", DEPLOY_SCRIPT],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log.info("deploy succeeded:\n%s", result.stdout[-2000:])
        else:
            log.error(
                "deploy failed (rc=%d):\n%s\n%s",
                result.returncode,
                result.stdout[-1000:],
                result.stderr[-1000:],
            )
    except subprocess.TimeoutExpired:
        log.error("deploy timed out")
    except Exception as exc:
        log.exception("deploy error: %s", exc)
    finally:
        _deploy_lock.release()


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default access log
        pass

    def do_POST(self):
        if self.path not in ("/hooks/deploy", "/hooks/deploy/"):
            self._reply(404, "not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        # Gitee sends the raw secret in X-Gitee-Token header
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
        log.info("push event ref=%r from %s", ref, self.client_address[0])

        # Fire deploy in background so we can respond quickly
        threading.Thread(target=_run_deploy, daemon=True).start()
        self._reply(200, "deploying")

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
    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), WebhookHandler)
    log.info("webhook server listening on port %d", PORT)
    server.serve_forever()
