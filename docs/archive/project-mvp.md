Project Goal

Build a minimal Cardiovascular Physician AI Assistant MVP using a Chinese LLM.

The MVP only supports:

Raw visit text input

Structured JSON extraction

EMR-ready note generation

Follow-up suggestion generation

No database.
No patient system.
No timeline.
No rule engine.
No WeChat integration.

Model Choice

Primary: DeepSeek-V3
Fallback: Qwen-Max

Use API-based inference.

Tech Stack

Python 3.11

FastAPI

Simple HTML frontend

requests or httpx

Environment variable for API key

Endpoints
POST /extract

Input:

{
  "raw_text": "..."
}

Process:
Call LLM with structured extraction prompt.

Output:
Structured JSON.

POST /generate-note

Input:

{
  "structured_json": {...}
}

Process:
Call LLM with note generation prompt.

Output:
{
"note_text": "...",
"follow_up_suggestions": [...]
}


---

## Structured JSON Schema

Must include:

- chief_complaint
- hpi
- vitals
- risk_factors
- medications
- labs
- imaging
- assessment
- plan

Missing fields must be null.

---

## Prompt Design

### Prompt 1 – Extraction

Role: Cardiovascular clinical assistant  
Output strictly JSON  
No hallucination  
Missing = null  

---

### Prompt 2 – Note Generation

Input: structured JSON  
Output:

Section 1: EMR-ready note  
Section 2: Follow-up checklist  

No invented data.

---

## UI

Single page:

- Large textarea (input)
- Button: Extract
- JSON viewer
- Button: Generate Note
- Output note area
- Copy button

---

## MVP Completion Criteria

- JSON extraction works reliably
- Note reads like real cardiology note
- Follow-up suggestions make clinical sense
- Runs locally
- API stable

---

End of MVP Plan

---

# 🧠 现在我要问你一个关键问题

你这个 MVP 是：

A. 只给自己测试  
B. 给 1-2 个真实心血管医生  
C. 准备上线国内市场  

如果是 A 或 B：

我们可以更简单。

如果是 C：

我们必须考虑：

- 数据合规
- 医疗AI监管
- 服务器部署在国内
- 数据不出境

这差别非常大。

---

你现在真正目标是哪一个？
