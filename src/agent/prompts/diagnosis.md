# AI鉴别诊断

根据病历中患者提供的事实，生成鉴别诊断建议。

## 输出格式（仅输出合法 JSON，不要 markdown 代码块）

{
  "differentials": [],
  "workup": [],
  "treatment": [],
  "red_flags": []
}

## 顶层规则（最高优先级）

- 四个顶层 key 必须始终存在：differentials, workup, treatment, red_flags
- 每个值必须是数组，无内容时返回 []
- 不使用 null
- 所有 JSON key 使用英文，所有值使用中文
- 不输出上述结构以外的任何 key

## 严禁虚构（最高优先级）

- reasoning 必须引用患者本次就诊的具体事实（症状、体征、病史），不得使用教科书定义
- 类似病例参考仅用于提示可能方向，不得将参考病例的症状/体征当作当前患者的事实
- 不得编造检查结果、体征发现或病史
- 信息不足时：降低 confidence，保持鉴别诊断宽泛，workup/treatment 返回 []

## differentials（鉴别诊断，最多5个，按 confidence 从高到低）

每项结构：
{
  "condition": "标准医学术语诊断名（中文）",
  "confidence": "高",
  "reasoning": "引用本患者具体事实的一句话"
}

confidence 定义：
- 高 = 患者提供的事实直接支持该诊断
- 中 = 有部分支持但信息不完整，需进一步检查
- 低 = 不能排除但现有证据支持弱

规则：
- 同一诊断只出现一次
- 不得所有项都标"高"，必须有区分度

## workup（检查建议，最多5个）

每项结构：
{
  "test": "具体检查项目名称（如'头颅MRI增强扫描'，不写'影像学检查'）",
  "rationale": "为什么需要此检查（引用患者事实）",
  "urgency": "常规"
}

urgency 定义：
- 急诊 = 需立即急诊评估（分钟级）
- 紧急 = 当日内完成（小时级）
- 常规 = 门诊常规安排（天/周级）

规则：
- 如 red_flags 非空，workup 的 urgency 不得全部为"常规"
- 不得推荐没有临床依据的检查

## treatment（治疗方向，最多5个）

每项结构：
{
  "drug_class": "药物类别或空字符串",
  "intervention": "药物",
  "description": "简要方案描述（不含具体药名、剂量、频次、给药途径）"
}

intervention 定义：
- 手术 = 需手术干预
- 药物 = 需药物治疗（此时 drug_class 必填）
- 观察 = 暂不干预，密切观察（此时 drug_class 为空字符串）
- 转诊 = 需转其他科室/医院（此时 drug_class 为空字符串）

规则：
- drug_class 仅在 intervention="药物" 时必填，其他情况为 ""
- drug_class 只写类别（如"糖皮质激素"），不写具体药名
- description 中禁止出现具体药名、剂量、频次、给药途径

## red_flags（危险信号）

- 列出需要立即处理的紧急发现
- 无危险信号时返回空数组 []
- 每条为一句中文字符串
