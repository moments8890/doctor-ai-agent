# 腾讯云部署总索引（1周内）

> 适用项目：`doctor-ai-agent`（FastAPI + WeChat + 前端）
>  
> 目标周期：7天内完成技术上线与灰度试运行（备案进入审核）
>  
> 当前日期：2026-03-05

## 使用方式

按以下顺序执行，每个子文档是可勾选的操作清单：

1. [00-前置检查与项目准备](./00-prerequisites.md)
2. [01-云资源开通与网络基建](./01-infra.md)
3. [02-服务部署（后端/前端/数据库/对象存储）](./02-deploy.md)
4. [03-GitHub 持续集成与持续部署（CI/CD）](./03-github-cicd.md)
5. [04-稳定在线与运维保障（高可用/监控/告警/备份）](./04-reliability.md)
6. [05-LLM 接入与主备切换（中国可用模型）](./05-llm.md)
7. [06-备案与合规执行清单](./06-compliance.md)
8. [07-上线日执行与回滚清单](./07-go-live.md)

部署工件目录：

1. `deploy/tencent/README.md` — 部署操作手册（当前生产配置）
2. `deploy/tencent/docker-compose.prod.yml` — 容器化备选方案
3. `deploy/tencent/nginx.conf` — 前端 Nginx 配置
4. `config/runtime.json.vm` — **生产运行时配置模板**（推荐，v2 结构化格式）
5. `deploy/tencent/runtime.example.json` — 生产配置参考（扁平格式）
6. `.github/workflows/ci.yml`
7. `.github/workflows/deploy-prod.yml`

## 里程碑（建议）

1. D1：完成 00 + 01（环境与资源就绪）
2. D2-D3：完成 02（最低可运行环境）
3. D4-D5：完成 03 + 05（自动化交付 + 模型接入）
4. D5-D6：完成 04 + 06（稳定性 + 合规动作落地）
4. D7：小流量灰度、复盘与下周扩容计划

## 交付完成标准

1. 外网 HTTPS 可访问，WeChat 回调可用
2. 代码 push 到 GitHub 后可自动发布到腾讯云
3. 服务具备监控、告警、备份和重启自恢复能力
4. 至少 2 个 LLM 提供商已接入并可自动降级切换
5. ICP/备案材料已提交并处于审核流转中
