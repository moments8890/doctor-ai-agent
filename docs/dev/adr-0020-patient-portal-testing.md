# ADR 0020 Post-Visit Patient Portal — Testing Plan

> Date: 2026-03-22 | Feature: Post-Visit Patient Portal
> Prerequisite: Seed data with at least 1 patient (李明), 1 doctor (张三),
> 1 intake record, 1 confirmed diagnosis with approved workup + treatment

---

## Part 1: Manual Testing Plan

### Setup Checklist

- [ ] Backend running on port 8000 (`uvicorn main:app --port 8000`)
- [ ] Frontend running on port 5173 (`cd frontend/web && npm run dev`)
- [ ] LLM server running (Ollama at LAN address or local)
- [ ] Seed patient 李明 with phone `13309292821`, YOB `1998`
- [ ] Seed doctor 张三 with confirmed diagnosis for 李明
- [ ] Generate access code for 李明 if needed

---

### Test Suite A: Patient Login & Navigation

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| A1 | Go to `/login`, click 患者 tab | Patient login form shown (昵称 + 口令) | |
| A2 | Login with phone `13309292821` + YOB `1998` | Redirects to `/patient`, 主页 tab active | |
| A3 | Tap 病历 tab | Shows record list with NewItemCard + records | |
| A4 | Tap 任务 tab | Shows task list or EmptyState | |
| A5 | Tap 设置 tab | Shows patient name + avatar + 退出登录 | |
| A6 | Tap back to 主页 | Chat tab with quick action cards + AI welcome | |
| A7 | Tap 退出登录 | Returns to login page, localStorage cleared | |

---

### Test Suite B: Chat — Triage Flow (requires LLM)

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| B1 | Type "我的药怎么吃" + Enter | AI answers with treatment context (informational) | |
| B2 | Check message appears with white bubble | AI response is left-aligned, white | |
| B3 | Type "吃了药头晕加重了" + Enter | AI asks follow-up questions (triage: symptom_report) | |
| B4 | Answer AI questions (severity, onset) | AI collects details, shows escalation card (yellow warning) | |
| B5 | Verify escalation card shows "已通知张医生" | Yellow card with structured symptom summary | |
| B6 | Switch to 病历 tab, then back to 主页 | Messages persist (loaded from server, not localStorage) | |

---

### Test Suite C: Chat — Graceful Degradation (LLM off)

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| C1 | Stop LLM server | Server still running, LLM unreachable | |
| C2 | Type "你好" + Enter | Green bubble appears, then AI responds "收到您的消息，医生将尽快回复您。" | |
| C3 | Verify NO 500 error in console | No error — graceful fallback | |
| C4 | Check message saved in DB | `patient_messages` has the inbound message with `source='patient'` | |

---

### Test Suite D: Chat — Polling & Doctor Replies

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| D1 | Patient sends a message | Message appears in patient chat | |
| D2 | Login as doctor (separate browser/tab) | Go to 患者 → click 李明 | |
| D3 | Scroll down to "患者消息" section | Shows patient's message in triage summary | |
| D4 | Click "查看完整对话" | Full thread expands with all messages | |
| D5 | Type a reply in doctor's reply input + 发送 | Reply appears in full thread | |
| D6 | Switch back to patient browser | Within 10s, doctor's reply appears as green-bordered DoctorBubble with "张三" name | |
| D7 | Switch patient to 病历 tab, wait 60s | Unread badge appears on 主页 tab if new messages arrive | |

---

### Test Suite E: Records — Diagnosis View

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| E1 | Go to 病历 tab | Record list shows diagnosis status badge per record | |
| E2 | Check badge for pending diagnosis | Yellow "诊断中" badge | |
| E3 | Check badge for completed (awaiting review) | Blue "待审核" badge | |
| E4 | Check badge for confirmed diagnosis | Green "已确认" badge | |
| E5 | Tap a record with confirmed diagnosis | Detail view shows structured fields + diagnosis card + treatment plan | |
| E6 | Verify diagnosis card has "已确认" StatusBadge | Green badge with diagnosis name | |
| E7 | Verify treatment plan shows medications | "用药：" section with drug names | |
| E8 | Verify signal flag warning card | Red-bordered card with "注意事项" if signal flags exist | |
| E9 | Tap a record with failed diagnosis | "诊断失败" red badge, no treatment plan | |

---

### Test Suite F: Tasks — Auto-Generation & Completion

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| F1 | As doctor: confirm a diagnosis with approved workup + treatment | Tasks auto-generated for patient | |
| F2 | As patient: go to 任务 tab | TaskChecklist shows pending tasks (检查, 用药, 复诊) | |
| F3 | Verify urgency badges | 紧急 tasks show red badge, 常规 show gray | |
| F4 | Verify due dates | Each task shows due date, overdue tasks in red | |
| F5 | Tap "上传" on a workup task | Upload flow triggers (file picker) | |
| F6 | Tap checkbox on a medication task | Task completes — green checkmark, strikethrough title | |
| F7 | Refresh page | Completed task stays completed, moves to "已完成" section | |
| F8 | Confirm same diagnosis again | No duplicate tasks created (dedupe) | |

---

### Test Suite G: Upload Matching

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| G1 | Patient uploads a lab result photo/PDF | Vision LLM extracts content | |
| G2 | System matches upload to pending task | Response includes `match.task_id` with confirmation text | |
| G3 | Patient confirms match | Task marked completed, doctor notified | |
| G4 | Upload unrelated file | No match, pending tasks list shown for manual selection | |

---

### Test Suite H: Notification & Rate Limiting

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| H1 | Patient sends clinical message → escalated | Doctor gets notification | |
| H2 | Patient sends 3 more clinical messages in same 6h window | 4th message saved but NO notification sent | |
| H3 | Patient gets "医生将在查看时一并处理您的问题" | Rate limit message shown | |
| H4 | Patient sends urgent message (signal flag) | Doctor notified immediately, bypasses rate limit | |
| H5 | Doctor confirms diagnosis | Patient sees "张三医生已确认您的诊断结果" in chat | |

---

### Test Suite I: Doctor — Patient Chat Panel

| # | Step | Expected Result | Pass? |
|---|------|----------------|-------|
| I1 | Go to 患者 → click a patient with messages | PatientDetail shows "患者消息" section | |
| I2 | Triage summary shows escalated messages only | Color-coded dots (red=urgent, blue=patient, green=AI) | |
| I3 | Click "查看完整对话" | Full thread with patient/AI/doctor messages labeled | |
| I4 | Type reply + Enter | Message sent, appears in thread with "医生" label | |
| I5 | Check patient with no messages | "暂无患者消息" empty state | |

---

## Part 2: Automated Testing Plan

### Layer 1: Unit Tests (mock all I/O)

| Test File | What it Tests | Priority |
|-----------|--------------|----------|
| `tests/unit/test_treatment_plan.py` | `derive_treatment_plan()` — parses ai_output + doctor_decisions JSON, returns correct approved items. Test with: all confirmed, all rejected, mixed, empty JSON, malformed JSON | High |
| `tests/unit/test_task_generation.py` | `generate_patient_tasks()` — correct task_type, due dates by urgency, dedupe logic, target='patient', source_type='diagnosis_auto'. Mock DB session. | High |
| `tests/unit/test_upload_matcher.py` | `match_upload()` — confidence thresholds, no-match fallback, multiple-match ambiguity. Mock LLM response. | Medium |
| `tests/unit/test_triage_handlers.py` | `handle_informational()`, `handle_escalation()`, `handle_urgent()` — message persistence, correct source/triage_category fields, rate limiting logic. Mock LLM + DB. | Medium |

### Layer 2: Integration Tests (safety-critical, mock LLM only)

| Test File | What it Tests | Priority |
|-----------|--------------|----------|
| `tests/integration/test_patient_triage.py` | **Triage classification safety**: clinical messages NEVER classified as informational. Test with: "头晕加重" → symptom_report, "我的药怎么吃" → informational, "胸痛呼吸困难" → urgent, "你好+我头疼" (ambiguous) → symptom_report. Mock LLM to return controlled JSON. | **Critical** |
| `tests/integration/test_patient_tasks_api.py` | Full API flow: create patient → confirm diagnosis → GET /api/patient/tasks returns auto-generated tasks → POST /complete marks done. Real DB, mock LLM. | High |
| `tests/integration/test_chat_endpoints.py` | POST /chat with mock triage → correct response shape. GET /chat/messages polling → returns messages in order. Doctor reply → appears in patient poll. | High |
| `tests/integration/test_diagnosis_confirm_tasks.py` | Confirm diagnosis → patient tasks created with correct target/source. Re-confirm → no duplicates. | High |
| `tests/integration/test_escalation_rate_limit.py` | 3 escalations in 6h → 4th suppressed. Urgent bypasses. 10-min batch window. | Medium |

### Layer 3: E2E / Chatlog Replay

| Test | What it Tests | Priority |
|------|--------------|----------|
| `tests/e2e/test_patient_portal_flow.py` | Full user journey: login → send message → view records → view diagnosis → complete task → upload result. Headless browser (Playwright). | High |
| `scripts/test.sh chatlog-patient` | Replay recorded patient conversations through POST /chat, verify triage categories match expectations. | Medium |

### Layer 4: Frontend Component Tests

| Test | What it Tests | Priority |
|------|--------------|----------|
| `DoctorBubble.test.jsx` | Renders doctor name + green border + content | Low |
| `TaskChecklist.test.jsx` | Renders pending/completed states, urgency badges, upload button on workup tasks, checkbox click calls onComplete | Medium |
| `PatientPage.test.jsx` | Tab switching, polling setup/teardown, message type rendering (patient/ai/doctor) | Low |

---

### Implementation Priority

```
Phase 1 (ship blocker):
  ✅ tests/integration/test_patient_triage.py        — safety-critical
  ✅ tests/unit/test_treatment_plan.py                — core data logic
  ✅ tests/unit/test_task_generation.py               — core data logic

Phase 2 (before doctor pilots):
  ✅ tests/integration/test_patient_tasks_api.py      — full API flow
  ✅ tests/integration/test_chat_endpoints.py         — messaging works
  ✅ tests/integration/test_escalation_rate_limit.py  — rate limiting

Phase 3 (quality):
  ✅ tests/e2e/test_patient_portal_flow.py            — full journey
  ✅ tests/unit/test_upload_matcher.py                — upload matching
  ✅ scripts/test.sh chatlog-patient                  — regression

Phase 4 (polish):
  ✅ Frontend component tests                         — optional
```

### Test Commands

```bash
# Run all patient portal tests
.venv/bin/python -m pytest tests/unit/test_treatment_plan.py tests/unit/test_task_generation.py tests/integration/test_patient_triage.py -v --rootdir=.

# Run safety-critical only
.venv/bin/python -m pytest tests/integration/test_patient_triage.py -v --rootdir=.

# Run full integration suite
.venv/bin/python -m pytest tests/integration/test_patient_*.py tests/integration/test_chat_*.py -v --rootdir=.

# E2E with headless browser
.venv/bin/python -m pytest tests/e2e/test_patient_portal_flow.py -v --rootdir=.
```

### Mock Patterns

```python
# Mock LLM for triage tests
@pytest.fixture
def mock_triage_llm(monkeypatch):
    async def fake_classify(text, context):
        if "头晕" in text or "疼痛" in text:
            return TriageResult(category=TriageCategory.symptom_report, confidence=0.9)
        if "胸痛" in text or "呼吸困难" in text:
            return TriageResult(category=TriageCategory.urgent, confidence=0.95)
        return TriageResult(category=TriageCategory.informational, confidence=0.8)
    monkeypatch.setattr("domain.patient_lifecycle.triage.classify", fake_classify)

# Mock DB session
@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(engine) as session:
        yield session

# Set ROUTING_LLM for dispatch mock
@pytest.fixture(autouse=True)
def mock_llm_env(monkeypatch):
    monkeypatch.setenv("ROUTING_LLM", "deepseek")
```
