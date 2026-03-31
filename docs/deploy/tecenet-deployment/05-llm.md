# 05｜LLM 接入与主备切换（中国可用模型）

## 目标

在腾讯云部署环境中完成中国可用 LLM 的稳定接入，并实现主备故障切换。

## 生产配置（2026-03-30 验证）

### 主：SiliconFlow — Qwen2.5-32B-Instruct

- **延迟**: 247ms（平均）
- **准确率**: 8/8（路由 4/4、提取 2/2、诊断 2/2）
- **价格**: ¥1.26/M input, ¥1.26/M output
- **优势**: 最快、非思考模型、稳定

### 备：DashScope（阿里云百炼）— qwen-turbo

- **延迟**: 379ms（平均）
- **准确率**: 8/8
- **价格**: ¥0.30/M input, ¥0.60/M output
- **优势**: 最便宜、阿里云自有服务

### 第二备：DeepSeek — deepseek-chat

- **延迟**: 847ms（平均）
- **准确率**: 8/8
- **价格**: ¥2.00/M input, ¥8.00/M output（缓存命中 ¥0.10）
- **优势**: 直连 API、缓存优惠

> 不推荐：Tencent LKEAP（延迟 >1.5s）、Qwen3/3.5 思考模型（延迟 >5s）

## 环境变量

```bash
# ── 主模型：SiliconFlow ──────────────────────
ROUTING_LLM=siliconflow
STRUCTURING_LLM=siliconflow
DIAGNOSIS_LLM=siliconflow
SILICONFLOW_API_KEY=sk-***
SILICONFLOW_MODEL=Qwen/Qwen2.5-32B-Instruct

# ── 备用：DashScope ──────────────────────────
DASHSCOPE_API_KEY=sk-***
DASHSCOPE_MODEL=qwen-turbo

# ── 第二备：DeepSeek ─────────────────────────
DEEPSEEK_API_KEY=sk-***
DEEPSEEK_MODEL=deepseek-chat

# ── 保留（不作为主模型）────────────────────
TENCENT_LKEAP_API_KEY=sk-***
TENCENT_LKEAP_MODEL=deepseek-v3.2
```

## 切换策略

### 降级顺序

```
SiliconFlow (Qwen2.5-32B) → DashScope (qwen-turbo) → DeepSeek (deepseek-chat)
```

### 切换条件

- 连续 3 次超时（>5s）或 5xx 错误
- API 返回空响应或 JSON 解析失败
- 429 限流超过 3 次/分钟

### 手动切换

```bash
# SSH 到生产服务器
ssh tencent

# 编辑 runtime.json
cd ~/doctor-ai-agent
python3 -c "
import json
with open('config/runtime.json') as f:
    c = json.load(f)
s = c['categories']['llm']['settings']
s['ROUTING_LLM']['value'] = 'dashscope'      # 切换到备用
s['STRUCTURING_LLM']['value'] = 'dashscope'
s['DIAGNOSIS_LLM']['value'] = 'dashscope'
with open('config/runtime.json', 'w') as f:
    json.dump(c, f, ensure_ascii=False, indent=2)
"

# 重启生效
sudo systemctl restart doctor-ai-backend
curl -s http://127.0.0.1:8000/healthz
```

## 模型评测对比（2026-03-30）

### 准确率（8 场景：4 路由 + 2 提取 + 2 诊断）

| 供应商 | 模型 | 得分 | 平均延迟 | 价格 ¥/M (入/出) |
|--------|------|:----:|--------:|:----------------:|
| **siliconflow** | **Qwen2.5-32B** | **8/8** | **1,239ms** | **1.26/1.26** |
| dashscope | qwen-turbo | 8/8 | 1,412ms | 0.30/0.60 |
| dashscope | qwen-plus | 8/8 | 2,598ms | 0.80/2.00 |
| siliconflow | Qwen2.5-72B | 8/8 | 4,001ms | 4.13/4.13 |
| deepseek | deepseek-chat | 8/8 | 4,487ms | 2.00/8.00 |
| tencent_lkeap | deepseek-v3 | 8/8 | 4,497ms | 2.00/8.00 |
| siliconflow | Qwen2.5-7B | 7/8 | 1,212ms | 免费 |
| tencent_lkeap | deepseek-v3.2 | 6/8 | 6,039ms | 2.00/3.00 |

### 延迟（最小 prompt，3 次取平均）

| 供应商 | 模型 | 平均延迟 | < 500ms |
|--------|------|--------:|:-------:|
| siliconflow | Pro/Qwen2.5-7B | 211ms | ✅ |
| siliconflow | Qwen2.5-7B | 224ms | ✅ |
| **siliconflow** | **Qwen2.5-32B** | **247ms** | **✅** |
| dashscope | qwen-turbo | 379ms | ✅ |
| siliconflow | Qwen2.5-14B | 388ms | ✅ |
| dashscope | qwen-plus | 863ms | ❌ |
| tencent_lkeap | deepseek-v3.1 | 1,593ms | ❌ |

## `/no_think` 策略

所有 prompt 文件首行包含 `/no_think`，禁用 Qwen3+ 思考模式。
Benchmark 和 Eval 端点对 `qwen3*` 模型自动传递 `enable_thinking: false`。

**生产避免使用思考模型** — 延迟增加 5-30s，对结构化输出任务无准确率提升。

## Debug Dashboard

```
https://api.doctoragentai.cn/api/debug/dashboard?token=<UI_DEBUG_TOKEN>#benchmark
```

- **Benchmark**: 延迟测试，支持模型下拉切换
- **Eval**: 8 场景准确率测试（路由 + 提取 + 诊断）
- 所有供应商并行运行，单次 5s 超时

## 验收 ✅

- [x] 主模型 SiliconFlow Qwen2.5-32B 延迟 <500ms
- [x] 8/8 准确率（路由、提取、诊断）
- [x] 备用 DashScope qwen-turbo 同样 8/8 准确率
- [x] 手动切换流程验证通过
- [ ] 自动降级切换（待实现 — 当前需手动切换）
