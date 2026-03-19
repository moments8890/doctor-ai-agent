# 05｜LLM 接入与主备切换（中国可用模型）

## 目标

在腾讯云部署环境中完成中国可用 LLM 的稳定接入，并实现主备故障切换。

## 供应商建议（本周可落地）

1. 主：DeepSeek API（兼容 OpenAI 风格）
2. 备：腾讯混元 API（同地域低延迟）
3. 可选第二备：阿里 DashScope（Qwen）或百度千帆

## 子清单

1. 模型路由策略
- [ ] 定义主备顺序：`primary -> secondary -> fallback`
- [ ] 定义切换条件：超时、5xx、限流、空响应
- [ ] 定义回切条件：连续 N 次成功后回切主模型

2. 项目配置映射（结合当前仓库）
- [ ] `ROUTING_LLM` 设为主路由模型
- [ ] `STRUCTURING_LLM` 设为高质量结构化模型
- [ ] 为每家供应商配置独立 API Key 与 endpoint
- [ ] 配置请求超时与重试上限

3. 腾讯混元接入
- [ ] 开通混元服务与密钥
- [ ] 在服务层新增 `hunyuan_client`（或统一 provider adapter）
- [ ] 完成最小调用闭环（文本问答 + 结构化输出）

4. DeepSeek 接入
- [ ] 配置 `DEEPSEEK_API_KEY`
- [ ] 验证与现有 `openai` 客户端兼容调用
- [ ] 测试医疗场景 prompt 稳定性

5. 质量与成本控制
- [ ] 建立固定评测集（心内/肿瘤真实样例）
- [ ] 比较维度：准确率、延迟、成本、稳定性
- [ ] 设置分场景路由：
- [ ] 高精度结构化 -> 成本更高模型
- [ ] 通用闲聊/低风险任务 -> 成本更低模型

6. 异常兜底
- [ ] 全部云模型失败时，返回可解释降级文案
- [ ] 可选：本地 Ollama 作为应急兜底（非主生产路径）
- [ ] 记录失败请求用于后续重放和分析

## 推荐环境变量（示例）

```bash
# 主备模型策略
ROUTING_LLM=deepseek
STRUCTURING_LLM=deepseek

# DeepSeek
DEEPSEEK_API_KEY=***

# 腾讯混元（示意，按你代码实际命名）
TENCENT_HUNYUAN_SECRET_ID=***
TENCENT_HUNYUAN_SECRET_KEY=***
TENCENT_HUNYUAN_REGION=ap-guangzhou

# 超时与重试（示意）
LLM_TIMEOUT_SECONDS=20
LLM_MAX_RETRIES=2
```

## 本步骤输出物

1. 《模型路由与降级策略》文档
2. 模型评测对比表（准确率/延迟/成本）
3. 生产配置模板（脱敏）

## 验收

- [ ] 主模型故障时可自动切换到备模型
- [ ] 单次请求延迟和失败率在目标阈值内
- [ ] 医疗结构化关键字段准确率达成团队目标

