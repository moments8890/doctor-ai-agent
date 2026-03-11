# Doctor AI Agent

Use `./dev.sh` as the single entrypoint for daily development tasks:

- `./dev.sh bootstrap`
- `./dev.sh vm-bootstrap --with-frontend --with-mysql`
- `./dev.sh vm-up`
- `./dev.sh vm-down`
- `./dev.sh start`
- `./dev.sh stop`
- `./dev.sh test <mode>`
- `./dev.sh e2e <half|full>`
- `./dev.sh data <preload|export-seed|import-seed|reset-from-seed> ...`
- `./dev.sh chat`
- `./dev.sh inspect-db`

## VM Commands (Separated Responsibilities)

- `./dev.sh vm-bootstrap --with-frontend --with-mysql`
  - One-time setup on a new VM.
  - Installs OS/toolchain dependencies and prepares local runtime prerequisites.
- `./dev.sh vm-up`
  - Runtime start only.
  - Starts MySQL container + backend + frontend processes.
  - Does not perform provisioning; if prerequisites are missing, run `vm-bootstrap`.

## Quick Flow

1. Bootstrap environment
```bash
./dev.sh bootstrap --with-frontend
```

2. Start local bundled services
```bash
./dev.sh start
```

Tencent Cloud Ubuntu (local source backend/frontend + docker MySQL + remote DeepSeek):
```bash
# one-time on a fresh VM
./dev.sh vm-bootstrap --with-frontend --with-mysql

# every time you want to run services
export DEEPSEEK_API_KEY="<your_deepseek_key>"
./dev.sh vm-up
```

Tencent LKEAP / DeepSeek via Tencent in-region endpoint:
```bash
export TENCENT_LKEAP_API_KEY="<your_tencent_lkeap_key>"
export TENCENT_LKEAP_MODEL="deepseek-v3-1"
./dev.sh vm-up --llm-provider tencent_lkeap
```

3. Run tests
```bash
./dev.sh test unit
./dev.sh test integration
./dev.sh e2e half
```

4. Manage dev data
```bash
./dev.sh data preload --doctor-id <doctor_id> --count 30 --with-records
./dev.sh data export-seed
./dev.sh data import-seed
./dev.sh data reset-from-seed
```

## Common Test Modes

- `unit`
- `integration`
- `integration-full`
- `chatlog-half`
- `chatlog-full`
- `all`

## Docs

- `docs/README.md`
- `docs/TESTING.md`
- `docs/review/architecture-overview.md`
- `docs/ai/AI提示词文档.md`
- `docs/ai/context-and-prompt-contract.md`
- `docs/adr/README.md`
- `AGENTS.md`

---

# 医生 AI 助手

日常开发统一使用 `./dev.sh`，不再分散执行多个脚本：

- `./dev.sh bootstrap`
- `./dev.sh start`
- `./dev.sh stop`
- `./dev.sh test <mode>`
- `./dev.sh e2e <half|full>`
- `./dev.sh data <preload|export-seed|import-seed|reset-from-seed> ...`
- `./dev.sh chat`
- `./dev.sh inspect-db`

## VM 命令职责拆分

- `./dev.sh vm-bootstrap --with-frontend --with-mysql`
  - 新 VM 上一次性执行
  - 安装系统/工具链依赖并准备运行前置条件
- `./dev.sh vm-up`
  - 仅负责运行时启动
  - 启动 MySQL 容器 + backend + frontend
  - 不做环境初始化；若缺依赖请先执行 `vm-bootstrap`

## 快速流程

1. 初始化环境
```bash
./dev.sh bootstrap --with-frontend
```

2. 启动本地整套服务
```bash
./dev.sh start
```

3. 执行测试
```bash
./dev.sh test unit
./dev.sh test integration
./dev.sh e2e half
```

4. 管理开发数据
```bash
./dev.sh data preload --doctor-id <doctor_id> --count 30 --with-records
./dev.sh data export-seed
./dev.sh data import-seed
./dev.sh data reset-from-seed
```

## 常用测试模式

- `unit`
- `integration`
- `integration-full`
- `chatlog-half`
- `chatlog-full`
- `all`

## 文档

- `docs/README.md`
- `docs/TESTING.md`
- `docs/review/architecture-overview.md`
- `docs/ai/AI提示词文档.md`
- `docs/ai/context-and-prompt-contract.md`
- `docs/adr/README.md`
- `AGENTS.md`
