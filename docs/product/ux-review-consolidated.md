# UX Review — Consolidated Findings

**Date:** 2026-03-09
**Method:** 6 independent AI agents reviewing codebase from different perspectives (clinical workflow, patient safety, busy clinic day friction, response quality/mobile UX, discoverability/learnability, PM product fit)
**Scope:** WeChat/WeCom KF message pipeline + Web UI (DoctorPage.jsx)

---

## Overall Ratings

| Agent Perspective | Rating |
|---|---|
| Clinical workflow expert | 5.5/10 |
| Patient safety reviewer | 5.5/10 |
| Busy clinic day (8hr simulation) | 6.5/10 |
| PM / response quality / mobile UX | 7/10 |
| First-time user / discoverability | 4/10 |
| Learnability | 3/10 |
| **Average** | **5.3/10** |

**Consensus:** Technically sound backend (async, durable, confirmation gate, audit trails). UX layer has multiple silent failure modes, dead UI elements, and near-zero discoverability. Not ready for non-technical doctor users without addressing P0/P1 items.

---

## What Works Well

- Fast router tiered design (Tier 0–3 + LLM fallback) — zero-latency clinical keyword detection
- Session chain continuation — follow-up dictations without repeating patient name
- CVD specialty context card — dense, structured, color-coded mRS scoring
- Draft confirmation gate architecture (pending → confirm → committed) — correct clinical practice
- Mobile split-view layout in PatientsSection
- Empty state with clickable chip on patient search — best UX moment in codebase; template for all other empty states
- Error messages that include syntax examples (lines 101, 447, 789 of wechat_domain.py)

---

## Priority Action Items

### P0 — Quick wins (30min–1hr each), implement immediately

| # | Issue | Where | Finding Source |
|---|-------|--------|----------------|
| 1 | **Risk filter dropdown is dead UI** — feature removed but control still renders, silently does nothing | `DoctorPage.jsx:762` | All 6 agents |
| 2 | **Draft footer missing "确认" keyword** — shows only "「撤销」可取消", doctor has no idea "确认" saves | `utils/response_formatting.py` | 3 agents |
| 3 | **Timeout WeChat reply misleading** — "正在处理，请稍候再发" implies retry, risks duplicate records | `routers/wechat.py:937` | 3 agents |
| 4 | **Location/link ACK promises follow-up that never arrives** — wires expectation with no delivery | `routers/wechat.py:1177,1185` | PM agent |
| 5 | **Gender shows raw "male"/"female" in patient list** — detail view shows 男/女, list shows English | `DoctorPage.jsx:811` | 2 agents |
| 6 | **Add "帮助" fast-route** — no help command on either channel; ~70% of features undiscoverable | `fast_router/_router.py` | 2 agents |
| 7 | **Home stat cards not clickable** — tapping "5 待处理任务" should navigate to task list | `DoctorPage.jsx:1480` | 2 agents |

### P1 — Half-day effort, adoption critical

| # | Issue | Where | Finding Source |
|---|-------|--------|----------------|
| 8 | **Task create: numeric patient ID field** — doctors never know internal DB IDs; practically unusable | `DoctorPage.jsx:1114` | 4 agents |
| 9 | **Auto-save has no "已自动保存" reply** — doctor never knows if record was committed on context switch | `routers/wechat.py:552-553` | 3 agents |
| 10 | **No WeChat welcome/onboarding on first contact** — first message is silence or generic 3-capability blurb | `routers/wechat.py` (missing) | 2 agents |
| 11 | **Specialty scale extraction missing from chat flow** — `extract_specialty_scores()` not called in `handle_add_record()`; NIHSS/mRS/UPDRS saves as free text in WeChat dictation | `services/wechat/wechat_domain.py:handle_add_record` | PM agent, feature-gap-analysis |
| 12 | **Draft TTL countdown missing from web UI banner** — doctor doesn't know draft will expire; no dismiss button | `DoctorPage.jsx:1833` | 2 agents |
| 13 | **import silently truncates beyond 10 chunks** — doctor pastes 15 records, last 5 dropped with no warning | `wechat_domain.py:1262` | PM agent |

### P2 — Nice-to-have, quality of life

| # | Issue | Where |
|---|-------|--------|
| 14 | Add "🟢 当前患者：张三" status line after context switches in WeChat | `wechat_domain.py` responses |
| 15 | Onboarding dialog should collect specialty — affects routing quality for all new web users | `DoctorPage.jsx:1912` |
| 16 | Settings: add profile edit after onboarding (specialty + name not editable post-signup) | `DoctorPage.jsx:SettingsSection` |
| 17 | Contextual examples in all error messages — ~50% currently have no actionable example | `wechat_domain.py` error strings |
| 18 | Record edit dialog exposes only 2 fields (content, type) — diagnosis/scores/dates not editable via UI | `DoctorPage.jsx:RECORD_FIELDS` |
| 19 | Chat history stored in localStorage only — lost on new device, unlimited growth risks cap | `DoctorPage.jsx:1202,1228` |
| 20 | `/加入知识库` command is completely undiscoverable — no menu entry, no examples | `fast_router/_router.py` |
| 21 | CVD scale auto-trigger is a "surprise" — doctor not told a multi-question scale will appear after certain records | `wechat_domain.py` |
| 22 | Background task auto-creation is invisible — doctor doesn't know follow-up tasks were created | `wechat_domain.py` |
| 23 | Frontend 15s timeout vs backend 4.5s — WeChat and web channels diverge; doctor gets conflicting status | `api.js:35`, `routers/wechat.py:INTENT_BG_TIMEOUT` |
| 24 | Label picker popover has no dismiss-on-outside-click — no escape on mobile | `DoctorPage.jsx:560-612` |

---

## Safety / Data Integrity Issues (from Patient Safety Agent)

| Issue | Severity | Notes |
|-------|----------|-------|
| `update_record` has no confirmation gate and no audit entry | 🔴 High | Direct update with no pending gate; inconsistent with add_record pattern |
| Emergency records bypass all confirmation — no explanation to doctor | 🟠 Medium | `wechat_domain.py:196-205`; doctor doesn't know it was permanent immediately |
| Same-name patient disambiguation missing in `add_record` | 🟠 Medium | Multiple patients named 张三 — which one? |
| Risk filter UI present but system is deferred — shows dead controls | 🟠 Medium | All 6 agents flagged |

---

## Discoverability Analysis (from Discoverability Agent)

Percentage of intents discoverable by channel:

| Discovery Method | Coverage |
|---|---|
| WeChat menu buttons (3 of ~15 intents have examples) | ~20% |
| LLM fallback response text | ~33% |
| Natural language trial-and-error | ~47% |
| Hidden / requires reading docs | ~13% |

Fast router tier visibility to doctor:
- Tier 0–1 (keyword/regex): visible via menu examples
- Tier 2–3 (clinical keywords, ML classifier): **invisible** — makes latency feel random
- Same message sometimes 0.1ms (Tier 0), sometimes 4s (LLM) — no indication why

---

## Feature Status (from PM Agent)

| Feature | Status | Notes |
|---------|--------|-------|
| 病历结构化 (record structuring) | ✅ Working | Text + voice + image OCR |
| 患者管理 (patient management) | ✅ Working | Create / query / delete |
| 随访任务 (follow-up tasks) | ✅ Working | Auto-create + manual |
| 确认审核门 (confirmation gate) | ✅ Working | pending → confirm → committed |
| 审计日志 (audit trails) | ✅ Working | Invisible to doctor |
| **专科量表提取 (specialty scale extraction)** | ❌ **Missing in chat** | Only works in PDF/Word import; #1 adoption blocker for neurologists |
| 初诊/复诊模板 (encounter type templates) | ⚠️ Partial | detect_encounter_type() exists but not surfaced in draft preview |
| PDF导出 (PDF export) | ✅ Working | With fallback warnings |
| 量表趋势图 (scale trend charts) | ❌ Not built | Blocked on specialty scale extraction |

---

## Already Fixed (This Session)

- Draft TTL 10 → 30 minutes
- Expiry message shows lost content (patient name + snippet)
- Draft preview format (`format_draft_preview()`)
- Pending record ID validation on hydration
- KF message durability (PendingMessage table)
- Clinical bypass in `handle_pending_create`
- Raw exception removed from PDF error message
- `task.description` → `task.content` in task cards
- Risk filter API param (`risk` not `category`)
- Patient list refresh after chat creates patient
- Session hydration upgraded to TTL-based (300s) for multi-device support
- Interview and CVD scale state now persisted to DB and restored on hydration
