# Doctor AI Agent

Use `./dev.sh` as the single entrypoint for daily development tasks:

- `./dev.sh bootstrap`
- `./dev.sh start`
- `./dev.sh stop`
- `./dev.sh test <mode>`
- `./dev.sh e2e <half|full>`
- `./dev.sh data <preload|export-seed|import-seed|reset-from-seed> ...`
- `./dev.sh chat`
- `./dev.sh inspect-db`

## Quick Flow

1. Bootstrap environment
```bash
./dev.sh bootstrap --with-frontend
```

2. Start local bundled services
```bash
./dev.sh start
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

- `docs/root/ARCHITECTURE.md`
- `docs/TESTING.md`
- `docs/ARCHITECTURE.zh.patient-data-model.md`
- `docs/README.md`
- `docs/root/AGENTS.md`

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

- `docs/root/ARCHITECTURE.md`
- `docs/TESTING.md`
- `docs/ARCHITECTURE.zh.patient-data-model.md`
- `docs/README.md`
- `docs/root/AGENTS.md`
