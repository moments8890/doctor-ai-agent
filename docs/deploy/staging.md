# Staging Environment Runbook

## What it is

Cheap pre-prod on the same CVM as prod. Reaches `app.stg.doctoragentai.cn`
+ `api.stg.doctoragentai.cn`. Backend on `:8001`, MySQL schema
`doctor_ai_staging`, working tree `/home/ubuntu/doctor-ai-staging/`.
Auto-deploys on push to `gitee/staging`.

WeChat appid `wx9667f8091b342fb7`. 开发版 routes to staging; 正式版 routes to
prod (unchanged). Only WeChat-listed 开发者/体验者 can scan 开发版 QR.

TLS: staging vhosts use `*.stg.doctoragentai.cn` wildcard cert (separate from
the prod `*.doctoragentai.cn` cert). See implementation plan Task 1b.

## Add a tester

WeChat 后台 → 成员管理 → 体验成员 → 添加成员 → paste WeChat ID.

## Deploy to staging server

Just push:

    git checkout staging
    # ... edits ...
    git push gitee staging

Webhook → `deploy-staging.sh` (under `staging-build.slice` cgroup, so it
can't starve prod). ~2-4 min total.

## Deploy to staging miniapp slot

After a server-side staging deploy, upload the WebView shell:

    git checkout staging
    git tag v1.x.y-staging-YYYY-MM-DD -m "<reason>"
    git push github v1.x.y-staging-YYYY-MM-DD

GitHub Actions → `miniprogram-staging.yml` (gated to staging branch). On phone,
open 开发版 from WeChat 后台 → 版本管理.

## Promote staging build to 正式版

Confirmed working in 开发版? Two equally valid paths:

A) **Re-tag the same commit on `main`** (cleanest):
   1. Merge `staging` to `main`.
   2. Tag `vX.Y.Z` on main.
   3. Push tag → `miniprogram-release.yml` uploads.
   4. WeChat 后台 → 版本管理 → 提交审核 → 发布 (~24h audit).

B) **Submit the existing 开发版 directly**: WeChat 后台 → 开发版 → find the
   `[STAGING]` build → 提交审核. Same .wxapkg goes to 正式版; runtime envVersion
   flips from `develop` to `release` so the bundle now points at prod URLs.
   Caveat: the build was tested against staging URLs only.

(A) is safer; (B) is faster. Default to A.

## Reset staging DB

Reproducible. Uses `systemd-run --property=EnvironmentFile=` so the DSN never
appears in `ps`/`/proc/<pid>/cmdline`.

    ssh ubuntu@CVM
    mysql -u root -p -e "DROP DATABASE doctor_ai_staging; CREATE DATABASE doctor_ai_staging CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    sudo systemd-run --pty --quiet --collect --uid=ubuntu \
      --working-directory=/home/ubuntu/doctor-ai-staging \
      --property=EnvironmentFile=/etc/doctor-ai-staging.env \
      /home/ubuntu/doctor-ai-staging/.venv/bin/alembic upgrade head
    sudo systemd-run --pty --quiet --collect --uid=ubuntu \
      --working-directory=/home/ubuntu/doctor-ai-staging \
      --property=EnvironmentFile=/etc/doctor-ai-staging.env \
      /home/ubuntu/doctor-ai-staging/.venv/bin/python scripts/ensure_welcome_code.py

## Tail logs

    ssh ubuntu@CVM
    tail -f /home/ubuntu/doctor-ai-staging/logs/backend.log
    tail -f /home/ubuntu/doctor-ai-staging/logs/deploy.log
    sudo journalctl -u doctor-ai-webhook -f

## Health checks

    curl https://api.stg.doctoragentai.cn/healthz
    curl -I https://app.stg.doctoragentai.cn/
    curl -s https://app.stg.doctoragentai.cn/wxABCDEF1234.txt   # WX-verify

## Resource caps

- Running staging service: `MemoryMax=2G`, `CPUQuota=150%` (in unit file).
- Staging deploy workload: `MemoryMax=4G`, `CPUQuota=200%`, `MemorySwapMax=0`
  (in `staging-build.slice`).

If staging starts misbehaving, check `systemctl status doctor-ai-staging` and
`systemd-cgls staging-build.slice`.

## Why same-CVM is "pre-prod" not "isolated staging"

Prod and staging share kernel, disk, MySQL instance, network, and (briefly)
deploy I/O. The cgroup caps minimize but don't eliminate this. For a true
isolation guarantee, move staging to a dedicated CVM.

## Renewal

The `*.stg.doctoragentai.cn` cert renews automatically via certbot (90-day
cycle). The renewal hook at `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`
reloads nginx after each successful renewal.

To force-renew during a debug session:

    sudo certbot renew --cert-name stg.doctoragentai.cn --force-renewal
    sudo systemctl reload nginx
