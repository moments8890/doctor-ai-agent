# 02｜服务部署（后端/前端/数据库）

## 目标

在 1-2 天内把本项目从本地开发态部署到腾讯云生产可运行态。

## 当前生产部署方式

**源码部署（非 Docker）**，运行在 Ubuntu CVM + systemd。

| 项目 | 值 |
|---|---|
| 服务器 | `ubuntu@101.35.116.122` |
| 应用目录 | `/home/ubuntu/doctor-ai-agent` |
| 后端服务 | `doctor-ai-backend`（systemd） |
| 自动部署 | `git push gitee main` 触发 webhook → 自动拉取重启 |
| 数据库 | MySQL `127.0.0.1:3306` |

## 子清单

### 1. 运行时配置

- [x] 配置文件：`config/runtime.json`（gitignored，不入库）
- [x] 模板文件：`config/runtime.json.vm`（生产推荐模板，脱敏，入库）
- [x] 参考文件：`deploy/tencent/runtime.example.json`（扁平格式，可直接用于快速 bootstrap）
- [ ] 将 `config/runtime.json.vm` 复制到服务器，填写所有 `<PLACEHOLDER>` 值

**禁止**在生产服务器上创建 `.env` 或 `.env.prod` 文件，所有配置均通过 `config/runtime.json` 注入。

必填配置项（见 `config/runtime.json.vm` 注释）：

| Key | 来源 |
|---|---|
| `DEEPSEEK_API_KEY` | platform.deepseek.com |
| `TENCENT_LKEAP_API_KEY` | 腾讯云 LKEAP 控制台 |
| `DATABASE_URL` | MySQL 账号密码 |
| `WECOM_CORP_ID` / `WECOM_SECRET` | 企业微信 → 应用管理 |
| `WECHAT_TOKEN` / `WECHAT_AES_KEY` | 企业微信 → 应用回调配置 |
| `WECHAT_KF_SECRET` / `WECHAT_KF_OPEN_KFID` | 企业微信 → 客服 |
| `MINIPROGRAM_TOKEN_SECRET` | 随机生成 |
| `MINIPROGRAM_API_BASE_URL` | 公网 HTTPS 域名 |
| `UI_ADMIN_TOKEN` | 随机生成强密码（Admin UI 登录用） |

### 2. 首次部署步骤

```bash
ssh -i ~/.ssh/tencent/doctor-ai-prod-cvm-01.pem ubuntu@101.35.116.122
cd /home/ubuntu/doctor-ai-agent
git pull gitee main

# Python 环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置
cp config/runtime.json.vm config/runtime.json
# 编辑 config/runtime.json，填入所有 <PLACEHOLDER> 值

# 前端构建
cd frontend && npm ci && npm run build && cd ..

# 启动服务
sudo systemctl enable doctor-ai-backend
sudo systemctl start doctor-ai-backend
sudo systemctl status doctor-ai-backend
```

### 2.5 数据库初始化（首次部署必做）

每次**清空数据库**或**首次部署**后，必须执行以下两个步骤，否则新用户无法注册，微信审核将失败。

```bash
cd /home/ubuntu/doctor-ai-agent

# 1. 创建 WELCOME 邀请码（无限次数，永不过期）
PYTHONPATH=src .venv/bin/python3 scripts/ensure_welcome_code.py

# 2. 创建微信审核测试账号 test / 123456
PYTHONPATH=src .venv/bin/python3 - <<'EOF'
import asyncio, os, sys
sys.path.insert(0, 'src')
from utils.app_config import load_config_from_json
_, vals = load_config_from_json()
for k, v in vals.items():
    if k not in os.environ:
        os.environ[k] = v
async def main():
    from infra.auth.unified import register_doctor
    try:
        r = await register_doctor('test', '测试医生', 123456, 'WELCOME')
        print(f"Test account created: {r['doctor_id']}")
    except Exception as e:
        print(f"Already exists or error: {e}")
asyncio.run(main())
EOF
```

> **微信审核要求（3.3.4）**：提审时填写测试账号 `test`，测试密码 `123456`。

### 2.6 升级现有数据库：人设数据迁移

**仅在从旧版本升级时需要执行**（旧版将人设存储在 `doctor_knowledge_items.category='persona'`，新版使用独立 `doctor_personas` 表）。

首次全新部署无需执行此步骤。

```bash
cd /home/ubuntu/doctor-ai-agent
# 先空跑确认影响范围
PYTHONPATH=src .venv/bin/python3 -m scripts.migrate_persona --dry-run
# 确认输出符合预期后正式执行
PYTHONPATH=src .venv/bin/python3 -m scripts.migrate_persona
```

### 3. 自动部署（Webhook）

```bash
# 本地触发部署
git push gitee main
```

Webhook 服务收到 Gitee push 事件后自动拉取并重启。参见 `deploy/tencent/setup_webhook.sh`。

### 4. 数据库

- [x] MySQL 运行于 `127.0.0.1:3306`
- [ ] 创建数据库和账号（见 `DATABASE_URL` 格式）
- [ ] 首次启动会自动建表（`create_tables()` 在 lifespan 中执行）
- [ ] 从 SQLite 迁移历史数据（如有）

### 5. 健康检查

```bash
curl -fsS http://127.0.0.1:8000/healthz
```

### 6. Admin UI

访问 `http://<server-ip>:5173/admin`（或配置的域名）。

登录需填写 `config/runtime.json` 中的 `UI_ADMIN_TOKEN`。

### 7. Docker Compose（备选方案）

如需容器化部署，参见 `deploy/tencent/docker-compose.prod.yml` 和 `nginx.conf`。

## 验收

- [ ] `curl http://127.0.0.1:8000/healthz` 返回 200
- [ ] WeChat 消息闭环可完成（文本/语音/图片）
- [ ] 新数据写入 MySQL，不再依赖本地 SQLite
- [ ] Admin UI 可通过 token 登录，可查看患者/病历数据
