# 01｜云资源开通与网络基建（腾讯云）

## 目标

在 1 天内完成可部署所需的最小云资源与网络安全底座。

## 子清单

1. 账号与权限
- [ ] 创建生产账号与操作员账号（禁止共享 root）
- [ ] 开启 MFA
- [ ] 创建 CAM 角色：`deploy-role`、`ops-readonly-role`
- [ ] 配置最小权限策略（CVM/TKE/TCR/COS/CLB/WAF/CDB/CLS/Monitor）

2. 地域与可用区
- [ ] 选择主地域（建议：`ap-guangzhou` 或 `ap-shanghai`）
- [ ] 选择至少 2 个可用区（后续高可用）
- [ ] 固化资源命名规范：`doctor-ai-{env}-{region}-{service}`

3. 网络
- [ ] 创建 VPC（例如 `10.10.0.0/16`）
- [ ] 创建子网：`public-subnet`、`app-subnet`、`db-subnet`
- [ ] 创建安全组并收敛端口：
- [ ] 入站只放行 `80/443` 给 CLB，`22` 仅堡垒机白名单
- [ ] 出站仅放行业务必要地址（WeChat API、LLM API、系统更新）

4. 核心云资源
- [ ] 计算层二选一：
- [ ] 快速上线：CVM + Docker
- [ ] 标准化：TKE（推荐）
- [ ] 数据库：TencentDB for MySQL/PostgreSQL（替代 SQLite）
- [ ] 对象存储：COS（语音、图片、导出文件）
- [ ] 镜像仓库：TCR（用于部署镜像）
- [ ] 负载均衡：CLB（公网入口）
- [ ] 证书：SSL 证书申请并绑定域名
- [ ] WAF（建议上线前启用）

5. 域名与回调准备
- [ ] 购买/接入域名，例如 `api.yourdomain.cn`
- [ ] DNS 解析到 CLB
- [ ] 规划 WeChat 回调路径：`/wechat`、健康检查路径：`/healthz`

6. 合规准备（并行推进）
- [ ] 准备 ICP 备案所需主体资料
- [ ] 确认服务器和域名满足备案前置要求
- [ ] 提交备案申请（目标：本周内进入审核）

## 本步骤输出物

1. 资源清单表（实例 ID、VPC、子网、安全组、CLB、DB、COS）
2. 《网络与端口基线》文档
3. 域名 + HTTPS 可访问的空服务入口

## 验收

- [ ] 从公网 `curl https://api.yourdomain.cn/healthz` 返回 200
- [ ] WeChat 可访问公网回调地址（先用占位响应）

