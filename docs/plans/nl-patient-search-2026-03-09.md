# Natural Language Patient Search — Design Plan
**Date:** 2026-03-09

## Goal
Allow doctors to query patients using natural Chinese language, e.g.:
- 那个姓张的阿姨
- 那个得癌症的人
- 上周刚来的高血压患者
- 60多岁的男性脑卒中

---

## Query Types Supported

| Pattern | Example | Extracted Field |
|---------|---------|----------------|
| Surname | 姓张的，张阿姨 | `surname = "张"` |
| Gender hint | 阿姨/女士/奶奶 → female; 叔叔/大爷/男 → male | `gender = "F"/"M"` |
| Age hint | 60多岁, 五十几岁, 中年 | `age_min`, `age_max` |
| Diagnosis keyword | 得癌症的, 高血压, 脑梗 | `keywords = ["癌", ...]` |
| Recency | 上周来的, 最近的 | `days_since_visit = 7` |
| Combined | 上周的那个姓李的高血压大叔 | all fields |

---

## Architecture — 3-Layer Pipeline

```
User query (natural language)
       │
       ▼
┌─────────────────────────────────┐
│  Layer 1: Rule Extractor        │  (services/patient/nl_search.py)
│  regex patterns → criteria dict │
└──────────────┬──────────────────┘
               │  PatientSearchCriteria
               ▼
┌─────────────────────────────────┐
│  Layer 2: SQL Search            │  (db/crud/patient.py)
│  patients JOIN medical_records   │
│  LIKE on tags + content         │
└──────────────┬──────────────────┘
               │  List[Patient]
               ▼
┌─────────────────────────────────┐
│  Layer 3: LLM Fallback          │  (only if 0 results from L2)
│  prompt LLM to extract criteria  │
│  re-run SQL                     │
└─────────────────────────────────┘
```

---

## Data Model

```python
# services/patient/nl_search.py

@dataclass
class PatientSearchCriteria:
    surname: str | None = None          # "张"
    gender: str | None = None           # "M" | "F"
    age_min: int | None = None          # 60
    age_max: int | None = None          # 69
    keywords: list[str] = field(default_factory=list)  # ["癌", "高血压"]
    days_since_visit: int | None = None  # 7 = last week
```

---

## Rule Extractor (Layer 1)

```python
FEMALE_HINTS = ["阿姨", "女士", "奶奶", "姐", "妈", "女"]
MALE_HINTS   = ["叔叔", "大爷", "爷爷", "哥", "爸", "男"]

RECENCY_MAP = {
    "昨天": 1, "最近": 3, "这两天": 2,
    "上周": 7, "下周": 7,  # "上周来的" = visited in last 7 days
    "这周": 7, "本周": 7,
    "这个月": 30, "上个月": 30,
}

def extract_criteria(query: str) -> PatientSearchCriteria:
    criteria = PatientSearchCriteria()

    # Surname: 姓X / X阿姨 / 那个X先生
    m = re.search(r'姓([^\s，,的]{1,2})', query)
    if m:
        criteria.surname = m.group(1)

    # Gender
    if any(h in query for h in FEMALE_HINTS):
        criteria.gender = "F"
    elif any(h in query for h in MALE_HINTS):
        criteria.gender = "M"

    # Age: 60多岁, 五六十岁, 中年(35-55), 老年(60+)
    m = re.search(r'(\d{2})多岁', query)
    if m:
        base = int(m.group(1))
        criteria.age_min, criteria.age_max = base, base + 9
    elif "中年" in query:
        criteria.age_min, criteria.age_max = 35, 55
    elif "老年" in query or "老人" in query:
        criteria.age_min = 60

    # Keywords: extract medical nouns (diagnosis / treatment terms)
    # Simple approach: any 2–6 char word that isn't a stopword
    MED_STOPWORDS = {"那个", "这个", "患者", "病人", "一个", "的人", "来的"}
    tokens = re.findall(r'[\u4e00-\u9fa5]{2,6}', query)
    criteria.keywords = [
        t for t in tokens
        if t not in MED_STOPWORDS
        and t not in {criteria.surname or ""}
        and not any(h in t for h in FEMALE_HINTS + MALE_HINTS)
    ]

    # Recency
    for phrase, days in RECENCY_MAP.items():
        if phrase in query:
            criteria.days_since_visit = days
            break

    return criteria
```

---

## SQL Search (Layer 2)

```python
# db/crud/patient.py — add search_patients_nl()

async def search_patients_nl(
    session: AsyncSession,
    doctor_id: str,
    criteria: PatientSearchCriteria,
    limit: int = 20,
) -> list[Patient]:
    q = select(Patient).where(Patient.doctor_id == doctor_id)

    if criteria.surname:
        q = q.where(Patient.name.like(f"{criteria.surname}%"))

    if criteria.gender:
        q = q.where(Patient.gender == criteria.gender)

    if criteria.age_min is not None:
        q = q.where(Patient.age >= criteria.age_min)
    if criteria.age_max is not None:
        q = q.where(Patient.age <= criteria.age_max)

    if criteria.keywords or criteria.days_since_visit:
        since = (
            datetime.utcnow() - timedelta(days=criteria.days_since_visit)
            if criteria.days_since_visit else None
        )
        rec_q = select(MedicalRecordDB.patient_id).where(
            MedicalRecordDB.doctor_id == doctor_id
        )
        if criteria.keywords:
            kw_filters = [
                or_(
                    MedicalRecordDB.content.like(f"%{kw}%"),
                    MedicalRecordDB.tags.like(f"%{kw}%"),
                )
                for kw in criteria.keywords
            ]
            rec_q = rec_q.where(and_(*kw_filters))
        if since:
            rec_q = rec_q.where(MedicalRecordDB.created_at >= since)
        rec_q = rec_q.distinct()
        q = q.where(Patient.id.in_(rec_q))

    q = q.order_by(Patient.updated_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())
```

---

## API Endpoint

```python
# routers/ui/__init__.py — add:

@router.get("/api/manage/patients/search")
async def search_patients_endpoint(
    q: str = Query(...),
    doctor_id: str = Query(default="web_doctor"),
    authorization: str | None = Header(default=None),
):
    resolved = _resolve_ui_doctor_id(doctor_id, authorization)
    criteria = extract_criteria(q)
    async with AsyncSessionLocal() as db:
        patients = await search_patients_nl(db, resolved, criteria)
    return {"patients": [p.to_dict() for p in patients], "criteria": asdict(criteria)}
```

---

## Intent Handler (WeChat)

Add to `services/ai/intent.py`:
```python
class Intent(str, Enum):
    ...
    search_patients = "search_patients"
```

Handle in `routers/wechat.py`:
```python
elif intent == Intent.search_patients:
    query_text = msg.content
    criteria = extract_criteria(query_text)
    patients = await search_patients_nl(db, doctor_id, criteria)
    if not patients:
        reply = "没有找到匹配的患者。"
    elif len(patients) == 1:
        p = patients[0]
        reply = f"找到患者：{p.name}，{p.age}岁，{p.diagnosis or '无诊断'}"
    else:
        lines = [f"找到 {len(patients)} 位患者："]
        for p in patients[:5]:
            lines.append(f"- {p.name}，{p.age}岁")
        reply = "\n".join(lines)
    return TextReply(reply)
```

---

## UI Changes

**Option A (recommended):** Enhance existing patient list search box in `DoctorPage.jsx`.

- Search box already exists and filters by name
- Detect if query is NL (contains Chinese characters beyond a simple name):
  ```javascript
  const isNLQuery = /[的得了这那哪]{1}|姓|阿姨|叔叔|岁/.test(q);
  ```
- If NL: call `GET /api/manage/patients/search?q=...` instead of local filter
- Show results in the same patient list panel with subtle "搜索结果" label
- Add `searchPatients(doctorId, q)` to `api.js`

**Option B:** Dedicated search modal — more complex, not needed initially.

---

## Files to Create/Modify

| File | Action | Change |
|------|---------|--------|
| `services/patient/nl_search.py` | **Create** | `PatientSearchCriteria` + `extract_criteria()` |
| `db/crud/patient.py` | Modify | Add `search_patients_nl()` |
| `routers/ui/__init__.py` | Modify | Add `GET /api/manage/patients/search` |
| `services/ai/intent.py` | Modify | Add `search_patients` intent value |
| `routers/wechat.py` | Modify | Handle `search_patients` intent |
| `frontend/src/api.js` | Modify | Add `searchPatients()` |
| `frontend/src/pages/DoctorPage.jsx` | Modify | NL search mode in search box |

---

## Implementation Order

1. `services/patient/nl_search.py` — pure logic, no DB, easy to test
2. `db/crud/patient.py` — `search_patients_nl()`
3. `routers/ui/__init__.py` — REST endpoint (enables Postman testing)
4. Frontend `api.js` + `DoctorPage.jsx` — UI integration
5. WeChat intent (optional, lower priority)

---

## Test Cases

```python
assert extract_criteria("那个姓张的阿姨").surname == "张"
assert extract_criteria("那个姓张的阿姨").gender == "F"
assert extract_criteria("上周来的高血压患者").days_since_visit == 7
assert "高血压" in extract_criteria("上周来的高血压患者").keywords
assert extract_criteria("60多岁的男性").age_min == 60
assert extract_criteria("60多岁的男性").age_max == 69
assert extract_criteria("60多岁的男性").gender == "M"
```
