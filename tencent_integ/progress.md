# Tencent Cloud / WeChat KF Integration Progress

## Server
- **VM**: 101.35.116.122 (Tencent Cloud CVM, Ubuntu 22.04)
- **Code path**: `/home/ubuntu/doctor-ai-agent`
- **SSH key**: `~/.ssh/tencent/doctor-ai-prod-cvm-01.pem`

## Current Stack (as of 2026-03-08)
- Backend: uvicorn on port 8000, nohup, logs → `logs/backend.vm.log`
- MySQL: Docker container `doctor-ai-mysql`, port 3306 (localhost only)
- Cloudflare tunnel: free ephemeral tunnel (URL changes on restart)
- LLM: DeepSeek (routing + structuring), Tencent LKEAP fallback
- WeChat: WeCom KF mode (corp_id `ww9c1d2ea57364ffd0`, kf agent)

## WeChat KF Setup
- Mode: WeCom KF (`kf/sync_msg` polling on webhook callback)
- Callback event: `kf_msg_or_event`
- Messages processing: confirmed working (voice, text, image)
- Webhook URL: Cloudflare tunnel URL + `/wechat`

## Domain: doctorai.com
- Registrar: IONOS (nameservers: `ns1100.ui-dns.*`)
- DNSPod (Tencent): has A record `101.35.116.122` but NOT active (wrong nameservers)
- Status: **DNS not resolving to VM yet**
- Options:
  - Add A record directly in IONOS (fastest)
  - Switch nameservers to DNSPod (24-48h propagation)

## HTTPS / Public URL
- Current: Cloudflare free tunnel (ephemeral, URL changes on restart)
- Next step: Named Cloudflare tunnel (free, stable subdomain)
- Future (scale): Tencent CLB + domain

## Auto-Deploy Pipeline (COMPLETE, as of 2026-03-08)

### Flow
```
git push gitee main
  → Gitee webhook POST https://api.doctoragentai.cn/hooks/deploy
  → nginx proxy → VM:9000
  → webhook_server.py (verifies X-Gitee-Token)
  → /home/ubuntu/deploy.sh
  → git fetch + reset --hard origin/main + pip install + systemctl restart doctor-ai-backend
```
Manual fallback: `ssh vm 'bash ~/deploy.sh'`

### VM components (all installed & running)
| Component | Location | Purpose |
|---|---|---|
| `webhook_server.py` | `~/doctor-ai-agent/tencent_integ/webhook_server.py` | HTTP listener on port 9000 |
| `deploy.sh` | `/home/ubuntu/deploy.sh` | git pull + pip sync + service restart |
| systemd service | `/etc/systemd/system/doctor-ai-webhook.service` | keeps webhook_server alive, auto-starts on boot |
| env file | `/home/ubuntu/.webhook.env` | `WEBHOOK_SECRET`, `WEBHOOK_PORT=9000`, `DEPLOY_SCRIPT` |
| sudoers rule | `/etc/sudoers.d/doctor-ai-deploy` | passwordless `systemctl restart doctor-ai-backend` |
| deploy key | `~/.ssh/gitee_deploy_key` | SSH auth to Gitee (read-only) |
| nginx location | `/etc/nginx/sites-available/doctoragentai.cn` | proxies `/hooks/deploy` → `127.0.0.1:9000` |

### Gitee configuration (already done)
- **Deploy key**: `deploy_tecent` (ed25519, read-only) → `~/.ssh/gitee_deploy_key.pub`
- **Webhook**: POST `https://api.doctoragentai.cn/hooks/deploy`, event: Push, secret stored in `~/.webhook.env`

### Monitoring
```bash
sudo systemctl status doctor-ai-webhook
sudo journalctl -u doctor-ai-webhook -f   # live webhook request log
tail -f ~/doctor-ai-agent/logs/deploy.log # live deploy output
```

### Re-setup from scratch (new VM)
1. Clone repo, copy `tencent_integ/` files to VM
2. Run: `bash tencent_integ/setup_webhook.sh <webhook-secret>`
3. Add nginx location block (proxy `/hooks/deploy` → `127.0.0.1:9000`)
4. Add `~/.ssh/gitee_deploy_key.pub` to Gitee repo → Deploy Keys
5. Add Gitee webhook → `https://<domain>/hooks/deploy`

## Systemd Services (as of 2026-03-08)
Both services are enabled (auto-start on boot) and managed by systemd:
- `doctor-ai-backend` — uvicorn on port 8000
- `cloudflared-doctor` — Cloudflare ephemeral tunnel → port 8000

Manage with:
```bash
sudo systemctl status doctor-ai-backend cloudflared-doctor
sudo systemctl restart doctor-ai-backend
```

Get current tunnel URL:
```bash
grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' ~/doctor-ai-agent/logs/tunnel.log | tail -1
```

## WeChat KF Webhook URL (stable)
```
https://api.doctoragentai.cn/wechat
```

## HTTPS Setup (as of 2026-03-08)
- nginx reverse proxy on port 80/443 → localhost:8000
- Let's Encrypt SSL cert for api.doctoragentai.cn (auto-renews via certbot timer)
- Cloudflare tunnel disabled
- Config: /etc/nginx/sites-available/doctoragentai.cn

## Bugs Fixed
- Deadlock in `_handle_intent_bg`: `hydrate_session_state` called inside outer `get_session_lock` — moved it outside (commit 2777a08)
- Missing `services/observability/turn_log.py` not committed (commit ae8e965)
- Missing `jwt` package — installed via requirements.txt

## Open Items
- [ ] Tencent CLB when scaling to multiple instances
- [ ] doctorai.com still on IONOS (not resolving to VM) — not needed now
