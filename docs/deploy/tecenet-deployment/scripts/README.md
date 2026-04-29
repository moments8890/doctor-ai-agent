# Tencent Cloud Deployment — doctor-ai-agent

> **本文件**：部署操作手册（稳定，记录"怎么做"）
>
> **`progress.md`**：运维状态日志（实时更新，记录"现在什么状态"、已知问题、Open Items）
>
> 两者互补：README 是参考文档，progress.md 是活跃工作日志。

---

## 当前生产环境

| 项目 | 值 |
|---|---|
| 服务器 | `ubuntu@101.35.116.122`（腾讯云 CVM，Ubuntu 22.04） |
| 应用目录 | `/home/ubuntu/doctor-ai-agent` |
| SSH 密钥 | `~/.ssh/tencent/doctor-ai-prod-cvm-01.pem` |
| 后端服务 | `doctor-ai-backend`（systemd，uvicorn 监听 `127.0.0.1:8000`） |
| 数据库 | MySQL Docker 容器 `doctor-ai-mysql`，端口 3306（仅 localhost） |
| 对外域名 | `api.doctoragentai.cn`（nginx + Let's Encrypt SSL） |
| WeChat | WeCom KF 模式，回调 `https://api.doctoragentai.cn/wechat` |
| LLM | DeepSeek（路由+结构化），Tencent LKEAP 备用 |
| 自动部署 | `git push gitee tencent` → Gitee Webhook → `doctor-ai-webhook` 服务（post 2026-04-28 swap：main 部署到 staging，tencent 部署到 prod） |

---

## 脚本说明

| 文件 | 说明 |
|---|---|
| `deploy.sh` | 从 Gitee 拉取最新代码、同步依赖、重启后端服务。由 webhook 触发，也可手动执行。 |
| `setup_webhook.sh` | **首次安装**自动部署流水线（只跑一次）。安装 webhook 服务、sudoers 规则、systemd 服务。 |
| `webhook_server.py` | Gitee Webhook HTTP 监听器（端口 9000），验证 Token 后异步触发 deploy.sh。 |
| `doctor-ai-webhook.service` | systemd 服务定义，托管 webhook_server.py，开机自启、崩溃自动重启。 |
| `docker-compose.prod.yml` | 容器化备选方案（含后端+前端+MySQL），非当前生产方式。 |
| `nginx.conf` | 前端 Nginx 配置参考（SPA + `/api` 反代）。 |
| `runtime.example.json` | 生产配置扁平格式参考（快速 bootstrap 用）。 |

---

## 自动部署流程

分支模型（post 2026-04-28 swap）：`gitee/main` → staging，`gitee/tencent` → prod。

```
git push gitee tencent                 (prod 发布)
  → Gitee Webhook POST https://api.doctoragentai.cn/hooks/deploy
  → nginx 反代 → VM:9000
  → webhook_server.py（验证 X-Gitee-Token，按 ref 路由）
  → BRANCH_DEPLOYS["tencent"] = /home/ubuntu/deploy.sh
  → git fetch + reset --hard gitee/tencent + pip install + systemctl restart doctor-ai-backend

git push gitee main                    (日常 → staging)
  → 同样的 webhook，但路由到：
  → BRANCH_DEPLOYS["main"] = sudo systemd-run --slice=staging-build.slice ... deploy-staging.sh
  → 在 cgroup 下 build + restart doctor-ai-staging（端口 8001，独立 MySQL schema）
```

手动触发备用：
```bash
ssh -i ~/.ssh/tencent/doctor-ai-prod-cvm-01.pem ubuntu@101.35.116.122 'bash ~/deploy.sh'
```

---

## 运行时配置

**`config/runtime.json`** 是唯一配置文件（gitignored，不入库）。

使用 **`config/runtime.json.vm`** 作为生产模板（脱敏，已入库），复制后填写所有 `<PLACEHOLDER>`。

```bash
cp config/runtime.json.vm config/runtime.json
# 编辑填写所有占位符
```

**禁止**在服务器上创建 `.env` 或 `.env.prod`。

必填配置项：

| Key | 来源 |
|---|---|
| `DEEPSEEK_API_KEY` | platform.deepseek.com |
| `TENCENT_LKEAP_API_KEY` | 腾讯云 LKEAP 控制台 |
| `DATABASE_URL` | MySQL 账号密码（格式：`mysql+aiomysql://user:pass@127.0.0.1:3306/dbname?charset=utf8mb4`） |
| `WECOM_CORP_ID` / `WECOM_SECRET` | 企业微信 → 应用管理 |
| `WECHAT_TOKEN` / `WECHAT_AES_KEY` | 企业微信 → 应用回调配置 |
| `WECHAT_KF_SECRET` / `WECHAT_KF_OPEN_KFID` | 企业微信 → 客服 |
| `MINIPROGRAM_TOKEN_SECRET` | 随机生成强密码 |
| `MINIPROGRAM_API_BASE_URL` | `https://api.doctoragentai.cn` |
| `UI_ADMIN_TOKEN` | 随机生成强密码（Admin UI 登录用） |
| `NOTIFICATION_PROVIDER` | 生产填 `wechat`，本地开发填 `log` |

---

## 首次部署（新服务器）

```bash
ssh -i ~/.ssh/tencent/doctor-ai-prod-cvm-01.pem ubuntu@101.35.116.122

# 1. 克隆代码
git clone git@gitee.com:moments6674/doctor-ai-agent.git /home/ubuntu/doctor-ai-agent
cd /home/ubuntu/doctor-ai-agent

# 2. Python 环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 配置
cp config/runtime.json.vm config/runtime.json
# 编辑 config/runtime.json，填入所有占位符

# 4. 前端构建
cd frontend && npm ci && npm run build && cd ..

# 5. 安装 Webhook 自动部署
bash deploy/tencent/setup_webhook.sh <webhook-secret>
# 然后在 nginx 中添加 /hooks/deploy 代理块，在 Gitee 仓库添加 Webhook + Deploy Key

# 6. 启动后端服务（setup_webhook.sh 已安装 doctor-ai-webhook，另需安装后端服务）
sudo cp deploy/tencent/doctor-ai-backend.service /etc/systemd/system/  # 如有
sudo systemctl enable --now doctor-ai-backend
```

---

## 日常运维

```bash
# 查看服务状态
sudo systemctl status doctor-ai-backend doctor-ai-webhook

# 手动重启后端
sudo systemctl restart doctor-ai-backend

# 查看部署日志
tail -f ~/doctor-ai-agent/logs/deploy.log

# 查看 Webhook 请求日志
sudo journalctl -u doctor-ai-webhook -f

# 健康检查
curl -fsS http://127.0.0.1:8000/healthz
```

---

## Admin UI

访问 `https://api.doctoragentai.cn/admin`（或本地 `http://127.0.0.1:5173/admin`）。

登录需填写 `config/runtime.json` 中的 `UI_ADMIN_TOKEN`，Token 存储在浏览器 localStorage。

---

## Webhook 服务器组件（已安装）

| 组件 | 路径 | 用途 |
|---|---|---|
| `webhook_server.py` | `~/doctor-ai-agent/deploy/tencent/webhook_server.py` | HTTP 监听器，端口 9000 |
| `deploy.sh` | `/home/ubuntu/deploy.sh` | 拉取代码 + 重启服务 |
| systemd 服务 | `/etc/systemd/system/doctor-ai-webhook.service` | 守护 webhook_server，开机自启 |
| 环境变量 | `/home/ubuntu/.webhook.env` | `WEBHOOK_SECRET`、`WEBHOOK_PORT`、`DEPLOY_SCRIPT` |
| sudoers 规则 | `/etc/sudoers.d/doctor-ai-deploy` | 无密码 `systemctl restart doctor-ai-backend` |
| Gitee Deploy Key | `~/.ssh/gitee_deploy_key` | SSH 只读认证到 Gitee |
| nginx location | `/etc/nginx/sites-available/doctoragentai.cn` | 代理 `/hooks/deploy` → `127.0.0.1:9000` |
