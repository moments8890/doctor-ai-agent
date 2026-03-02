# Debug Iteration Log — 2026-03-01

## Training Run: cardiology_v1 (llama3.2)

**Result:** 17/20 passed

---

### Failed Cases

| Case | Patient | Field | Error |
|------|---------|-------|-------|
| 013 | 唐明 (间断心前区不适半年，轻度心肌缺血) | `auxiliary_examinations` | Input should be a valid string |
| 018 | 顾建军 (慢性心衰复诊，体重增加2kg) | `follow_up_plan` | Input should be a valid string |
| 020 | 孟凡 (血脂升高多年，间断胸闷) | `treatment_plan` | Input should be a valid string |

---

### Root Cause

`llama3.2` (and occasionally other models) returns multi-item fields as **JSON arrays or nested objects** instead of flat strings. For example:

```json
"treatment_plan": ["调整降脂药", "复查血脂", "建议饮食控制"]
```

instead of the expected:

```json
"treatment_plan": "调整降脂药；复查血脂；建议饮食控制"
```

This violates the system prompt instruction ("字段值为字符串或 null，不使用数组或嵌套对象") but smaller models do not reliably follow it. Fields most prone to this are those that naturally enumerate multiple items: `treatment_plan`, `follow_up_plan`, `auxiliary_examinations`.

---

### Fix Applied

**File:** `services/structuring.py`

Added a post-parse coercion step before Pydantic validation. After `json.loads()`, iterate over all optional string fields and coerce non-string values:

- `list` → join with `；`
- `dict` → join as `key：value` pairs with `；`
- other → `str(val)`

```python
_STR_FIELDS = [
    "history_of_present_illness", "past_medical_history", "physical_examination",
    "auxiliary_examinations", "diagnosis", "treatment_plan", "follow_up_plan",
]
for field in _STR_FIELDS:
    val = data.get(field)
    if val is None or isinstance(val, str):
        continue
    if isinstance(val, list):
        data[field] = "；".join(str(item) for item in val if item)
    elif isinstance(val, dict):
        data[field] = "；".join(f"{k}：{v}" for k, v in val.items())
    else:
        data[field] = str(val)
```

This is model-agnostic: the coercion runs for all providers and models, so future model switches remain safe.

---

### Status

- [x] Fix implemented
- [ ] Re-run training to verify 20/20
