# 03｜GitHub 持续集成与持续部署（CI/CD）

## 目标

实现 `GitHub push -> 自动测试 -> 自动构建镜像 -> 自动部署腾讯云`。

## 子清单

1. GitHub 基础
- [ ] 分支策略：`main`（生产）、`develop`（集成）
- [ ] 保护规则：PR 必须通过测试后合并
- [ ] 添加 CODEOWNERS（可选）

2. GitHub Secrets
- [ ] `TCR_REGISTRY`
- [ ] `TCR_USERNAME`
- [ ] `TCR_PASSWORD`
- [ ] `TCR_IMAGE_PREFIX`
- [ ] `PROD_HOST`
- [ ] `PROD_USER`
- [ ] `PROD_SSH_PRIVATE_KEY`
- [ ] `PROD_DEPLOY_DIR`

3. CI 工作流（建议两个）
- [ ] `ci.yml`：安装依赖 + 单测 + 覆盖率门禁
- [ ] `deploy-prod.yml`：仅在 `main` 触发
- [ ] 构建镜像并 push 到 TCR
- [ ] 远端拉取新镜像并滚动重启服务
- [ ] 使用仓库内模板：
- [ ] `.github/workflows/ci.yml`
- [ ] `.github/workflows/deploy-prod.yml`

4. 部署策略
- [ ] 蓝绿或滚动发布（二选一）
- [ ] 每次发布都生成可追踪 tag（`git-sha`）
- [ ] 发布失败自动回滚上一版本

5. 验证
- [ ] PR 阶段自动跑 `bash scripts/test.sh unit`
- [ ] 合并 `main` 后 10 分钟内生产完成更新
- [ ] 发布后自动执行健康检查并写入状态

## 推荐流水线阶段

1. `lint/test`
2. `build-image`
3. `push-tcr`
4. `deploy-prod`
5. `post-deploy-smoke`

## 本步骤输出物

1. `.github/workflows/ci.yml`
2. `.github/workflows/deploy-prod.yml`
3. 回滚文档（失败处理 SOP）

## 验收

- [ ] 任意一次 `main` 合并都能自动部署
- [ ] 失败时可在 5 分钟内回滚
