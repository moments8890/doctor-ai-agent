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
cd frontend/web && npm run build
bash scripts/test.sh integration-full

# Benchmark / chatlog gates need local dataset files under e2e/fixtures/data/
# plus a dedicated backend instance on 8001.
./cli.py start --port 8001 --no-frontend &
bash scripts/test.sh hero-loop
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
- `integration-full`
- `chatlog-half`
- `chatlog-full`
- `hero-loop`
- `all`

`unit` still exists, but it is not the default development gate in the current
MVP phase.
`integration` is a stale legacy wrapper and should not be used in fresh clones.
`chatlog-*` and `hero-loop` require local benchmark fixtures under
`e2e/fixtures/data/`.

## Source of Truth — 5 Canonical Entrypoints

Each concern has one entrypoint. Start there, not in subfiles.

| Concern | Entrypoint | What it covers |
|---------|-----------|---------------|
| **Repo rules** | `AGENTS.md` | Code style, testing policy, push rules, planning, cascading impact checklist |
| **Architecture** | [`docs/architecture.md`](docs/architecture.md) | System layers, pipeline, DB schema, domain ops, prompt system, CDS pipeline, startup |
| **Product** | [`docs/product/index.md`](docs/product/index.md) | Strategy, roadmap, feature status, CDS product decisions → links to subfiles |
| **UI / UX** | [`docs/ux/UI-DESIGN.md`](docs/ux/UI-DESIGN.md) | Design system, components, tokens, patterns; links to `design-spec.md` for Chinese UX flows |
| **Dev ops** | [`docs/dev/index.md`](docs/dev/index.md) | Testing, deployment, LLM providers, patient sim, UI audit → links to subfiles |

### Interactive Visual Guides

Open in browser for draggable diagrams, hover tooltips, and filter controls.

| File | What it shows |
|------|-------------|
| [`docs/architecture-visual.html`](docs/architecture-visual.html) | System overview, pipeline flow, prompt stack, DB relationship graph, process model |
| [`docs/ux/page-force-graph.html`](docs/ux/page-force-graph.html) | Page navigation graph — all routes, cross-links, orphaned pages |
| [`docs/ux/UI-DESIGN-visual.html`](docs/ux/UI-DESIGN-visual.html) | Design system visual reference — components, tokens, patterns |
| [`docs/product/product-strategy-visual.html`](docs/product/product-strategy-visual.html) | Product strategy overview — north star, user personas, roadmap |

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
cd frontend/web && npm run build
bash scripts/test.sh integration-full

# Benchmark / chatlog 门槛依赖 e2e/fixtures/data/ 下的本地数据集，
# 并且需要单独的 8001 测试服务。
./cli.py start --port 8001 --no-frontend &
bash scripts/test.sh hero-loop
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
- `integration-full`
- `chatlog-half`
- `chatlog-full`
- `hero-loop`
- `all`

`unit` 仍然可用，但在当前 MVP 阶段不作为默认开发门槛。
`integration` 现在是遗留包装器，新的 clone 不要再用。
`chatlog-*` 和 `hero-loop` 依赖 `e2e/fixtures/data/` 下的本地基准数据集。

## 权威文档 — 5 个入口

每个关注点有一个入口文件，从这里开始。

| 关注点 | 入口 | 覆盖范围 |
|--------|-----|---------|
| **仓库规则** | `AGENTS.md` | 代码风格、测试策略、推送规则、计划规则、级联影响清单 |
| **架构** | [`docs/architecture.md`](docs/architecture.md) | 系统分层、流水线、数据库、领域操作、提示词系统、CDS流水线、启动流程 |
| **产品** | [`docs/product/index.md`](docs/product/index.md) | 战略、路线图、功能状态、CDS产品决策 → 链接到子文件 |
| **UI / UX** | [`docs/ux/UI-DESIGN.md`](docs/ux/UI-DESIGN.md) | 设计系统、组件、令牌、模式；链接到 `design-spec.md`（中文UX流程） |
| **开发运维** | [`docs/dev/index.md`](docs/dev/index.md) | 测试、部署、LLM配置、患者模拟、UI审计 → 链接到子文件 |

### 交互式可视化

用浏览器打开，支持拖拽、悬浮提示、筛选。

| 文件 | 内容 |
|------|------|
| [`docs/architecture-visual.html`](docs/architecture-visual.html) | 系统架构、流水线、提示词栈、数据库关系图、进程模型 |
| [`docs/ux/page-force-graph.html`](docs/ux/page-force-graph.html) | 页面导航图 — 路由、跨页链接、孤立页面 |
| [`docs/ux/UI-DESIGN-visual.html`](docs/ux/UI-DESIGN-visual.html) | 设计系统参考 — 组件、令牌、模式 |
| [`docs/product/product-strategy-visual.html`](docs/product/product-strategy-visual.html) | 产品策略概览 — 北极星、用户画像、路线图 |
