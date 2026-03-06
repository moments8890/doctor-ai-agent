# 02｜服务部署（后端/前端/数据库/对象存储）

## 目标

在 1-2 天内把本项目从本地开发态部署到腾讯云生产可运行态。

## 子清单

1. 部署方式选择
- [ ] 选择 `CVM + Docker Compose`（最快）
- [ ] 或选择 `TKE + Helm`（推荐长期）
- [ ] 本周建议：先 CVM，后续平滑迁移 TKE

2. 项目容器化
- [ ] 新增后端 `Dockerfile`（FastAPI + Uvicorn）
- [ ] 前端独立构建（Vite build）并由 Nginx 托管
- [ ] 增加 `.dockerignore`
- [ ] 增加 `docker-compose.prod.yml`（若走 CVM 方案）
- [ ] 使用仓库内模板：
- [ ] `Dockerfile`
- [ ] `frontend/Dockerfile`
- [ ] `deploy/tencent/nginx.conf`
- [ ] `deploy/tencent/docker-compose.prod.yml`
- [ ] `deploy/tencent/runtime.prod.example.json`

3. 配置与密钥
- [ ] 建立生产环境变量清单（`.env.prod` 不入库）
- [ ] 配置关键变量：
- [ ] `DATABASE_URL`（改用 TencentDB）
- [ ] `WECHAT_*`（公众号/客服回调）
- [ ] `DEEPSEEK_API_KEY` / `TENCENT_HUNYUAN_*`（后续 LLM）
- [ ] `PATIENTS_DB_PATH` 仅保留本地回退，不作为生产主路径
- [ ] 使用腾讯云密钥管理（或最小化先用主机安全注入）

4. 数据库迁移（重点）
- [ ] 从 SQLite 导出现有必要数据
- [ ] 在 TencentDB 创建生产库与账号
- [ ] 修改 SQLAlchemy 连接字符串，验证建表与读写
- [ ] 执行一次导入与校验（抽查患者/病历/任务）

5. COS 集成
- [ ] 新增对象存储桶（按环境分桶）
- [ ] 设置生命周期策略（冷热分层、过期删除）
- [ ] 语音/图片上传改为 COS 地址持久化
- [ ] 配置私有读写与临时签名下载

6. 上线与回滚
- [ ] 发布 `v0` 到生产
- [ ] 配置健康检查：`/healthz`
- [ ] 发布后做冒烟：
- [ ] 文本消息 -> 病历入库
- [ ] 语音消息 -> 转写 -> 入库
- [ ] 图片消息 -> 结构化 -> 入库
- [ ] 准备回滚：保留上一镜像 tag 与一键回滚脚本

## 本步骤输出物

1. 可重复部署文档（含命令）
2. 生产环境变量模板（脱敏）
3. 部署架构图（CLB -> App -> DB/COS）

## 验收

- [ ] 生产地址可完成一次完整 WeChat 闭环
- [ ] 新数据写入 TencentDB，不再依赖本地 SQLite
- [ ] 图片/语音文件可在 COS 查到对象
