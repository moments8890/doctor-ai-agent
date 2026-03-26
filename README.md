# Doctor AI Agent

Use `./cli.py` as the single entrypoint for server lifecycle:

- `./cli.py bootstrap`
- `./cli.py bootstrap --vm`
- `./cli.py start`
- `./cli.py start --prod`
- `./cli.py stop`

Testing and data scripts live in `scripts/`:

- `bash scripts/test.sh <mode>`
- `python scripts/chat.py`
- `python scripts/preload_patients.py`
- `python scripts/db_inspect.py`

## VM Commands

- `./cli.py bootstrap --vm`
  - One-time setup on a new VM.
  - Installs OS/toolchain dependencies, Docker, and MySQL container.
- `./cli.py start --prod`
  - Production startup.
  - Validates runtime config, checks MySQL, starts backend + frontend.

## Quick Flow

1. Bootstrap environment
```bash
./cli.py bootstrap
```

2. Start local bundled services
```bash
./cli.py start
```

Tencent Cloud Ubuntu (local source backend/frontend + docker MySQL + remote DeepSeek):
```bash
# one-time on a fresh VM
./cli.py bootstrap --vm

# every time you want to run services
export DEEPSEEK_API_KEY="<your_deepseek_key>"
./cli.py start --prod --provider deepseek
```

Tencent LKEAP / DeepSeek via Tencent in-region endpoint:
```bash
export TENCENT_LKEAP_API_KEY="<your_tencent_lkeap_key>"
./cli.py start --prod --provider tencent_lkeap
```

3. Validate behavior
```bash
bash scripts/test.sh integration

# E2E chatlog replay targets port 8001 (not the default 8000 dev server).
# Start a dedicated backend instance on 8001 first:
./cli.py start --port 8001 --no-frontend &
bash scripts/test.sh chatlog-half
```

Current MVP policy: skip unit tests during normal development unless you are
doing explicit test work.

4. Manage dev data
```bash
python scripts/preload_patients.py --doctor-id <doctor_id> --count 30 --with-records
python scripts/seed_db.py --export
python scripts/seed_db.py --import
python scripts/seed_db.py --reset --import
```

## Common Validation Modes

- `unit`
- `integration`
- `integration-full`
- `chatlog-half`
- `chatlog-full`
- `all`

`unit` still exists, but it is not the default development gate in the current
MVP phase.

## Docs

- `AGENTS.md` — repo rules, documentation standards, code style, workflow
- `docs/README.md` — documentation index and folder map
- `docs/TESTING.md` — validation workflow and test modes
- `docs/review/architecture-overview.md` — current system architecture
- `docs/ux/UI-DESIGN.md` — UI design principles, component guide, file map
- `docs/product/feature-parity-matrix-2026-03-25.md` — frontend feature status
- `src/agent/prompts/README.md` — prompt architecture and intent routing

---

# 医生 AI 助手

日常开发统一使用 `./cli.py`：

- `./cli.py bootstrap`
- `./cli.py start`
- `./cli.py stop`

测试和数据脚本位于 `scripts/`：

- `bash scripts/test.sh <mode>`
- `python scripts/chat.py`
- `python scripts/preload_patients.py`
- `python scripts/db_inspect.py`

## VM 命令

- `./cli.py bootstrap --vm`
  - 新 VM 上一次性执行
  - 安装系统/工具链依赖、Docker 和 MySQL 容器
- `./cli.py start --prod`
  - 生产环境启动
  - 验证运行时配置、检查 MySQL、启动后端和前端

## 快速流程

1. 初始化环境
```bash
./cli.py bootstrap
```

2. 启动本地整套服务
```bash
./cli.py start
```

3. 验证行为
```bash
bash scripts/test.sh integration
bash scripts/test.sh chatlog-half
```

当前 MVP 阶段默认跳过单元测试；只有在明确做测试工作时才运行或修改单元测试。

4. 管理开发数据
```bash
python scripts/preload_patients.py --doctor-id <doctor_id> --count 30 --with-records
python scripts/seed_db.py --export
python scripts/seed_db.py --import
python scripts/seed_db.py --reset --import
```

## 常用验证模式

- `unit`
- `integration`
- `integration-full`
- `chatlog-half`
- `chatlog-full`
- `all`

`unit` 仍然可用，但在当前 MVP 阶段不作为默认开发门槛。

## 文档

- `AGENTS.md` — 仓库规则、文档标准、代码风格、工作流
- `docs/README.md` — 文档索引和目录结构
- `docs/TESTING.md` — 验证流程和测试模式
- `docs/review/architecture-overview.md` — 当前系统架构
- `docs/ux/UI-DESIGN.md` — UI设计规范、组件指南、文件索引
- `docs/product/feature-parity-matrix-2026-03-25.md` — 前端功能状态
- `src/agent/prompts/README.md` — 提示词架构和意图路由
