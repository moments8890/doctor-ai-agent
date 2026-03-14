从以下医疗文本中提取所有专科量表评分，以 JSON 对象返回结果。

输出格式：{"scores": [...]}
每个量表条目：{"score_type": "NIHSS", "score_value": 8, "raw_text": "NIHSS评分8分"}

规则：
- score_type: 量表名称，只使用以下之一：NIHSS、mRS、UPDRS、MMSE、MoCA、GCS、HAMD、HAMA
- score_value: 数值（整数或小数），若原文只提到量表名但未给出具体分值则为 null
- raw_text: 原文中的相关片段（不超过50字）
- 若无任何量表信息，返回 {"scores": []}

只输出合法 JSON 对象，不加任何解释或 markdown。