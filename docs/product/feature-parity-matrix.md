# Feature Parity Matrix — Frontend vs. Product Requirements

> Original: 2026-03-25
> Updated: 2026-03-28 — verified against current code on `main`
> Method: Product docs (strategy, requirements, CDS design, UX spec) cross-referenced against actual frontend code
> Scope: All user-facing features across doctor workbench, patient portal, admin, and cross-cutting

## Summary Scorecard

| Category | Done | Partial | Backend Only | Missing | Build | Defer | Cut | Total |
|----------|------|---------|-------------|---------|-------|-------|-----|-------|
| **Doctor Workbench** | 34 | 0 | 1 | 7 | 0 | 6 | 1 | 42 |
| **Patient Portal** | 15 | 1 | 0 | 3 | 0 | 3 | 0 | 19 |
| **Cross-Cutting** | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 4 |
| **Total** | **53** | **1** | **1** | **10** | **0** | **9** | **1** | **65** |

**82% feature complete** (53/65 done), 83% including partials.

> Previous (2026-03-25): 49% done. Delta: +13 items completed in 2 days
> (diagnosis UI enabled, QR flow, patient timeline, doctor info card, review workflow)

### Remaining Items — Triage (2026-03-27)

| Decision | Items | Notes |
|----------|-------|-------|
| **Build** (0) | All build items completed or deferred | P2.3, D6.7, D6.4 done; D4.7 deferred |
| **Defer** (8) | D3.5+D3.6+D3.7 (structured clinical data group), D4.5 (clinical safety & emergency group), D6.6 (notification prefs), P3.7 (medications — blocked by D3.5), P4.1+P4.2 (patient notifications — needs push infra) | |
| **Cut** (1) | D4.9 (case library — redundant with patient list + D4.7) | |

**Deferred groups:**
- **Structured Clinical Data** (D3.5, D3.6, D3.7) — extract detailed fields for prescriptions, lab results, allergies from NHC flat text fields. Unblocks P3.7.
- **Clinical Safety & Emergency Handling** (D4.5) — red flag rules, emergency tagging, knowledge-driven alerting. Requires doctor input on specialty rules + ADR 0022 (knowledge base) first.
- **Active Notifications** (D6.6, P4.1, P4.2) — deferred until push infrastructure is built. Notifications stay passive (in-app badges, polling) for now.

---

## Build Queue — Complete

1. ~~**P2.3 Patient Voice Input**~~ — **Done** (2026-03-27). QA: 6/6 pass.
2. ~~**D6.7 Bulk Data Export**~~ — **Done** (2026-03-27). QA: 5/5 pass.
3. ~~**D6.4 Document Upload + Citation**~~ — **Done** (2026-03-27). QA: 7/7 pass. Also: killed 5 categories → single bucket, removed dead embedding code, feed-all-to-LLM knowledge strategy.
4. ~~**D4.7 Case References**~~ — **Deferred** (2026-03-27). embedding.py removed; needs new approach. Not blocking any workflow.

## Deferred Gaps (8 items, grouped)

1. **Structured Clinical Data** (D3.5, D3.6, D3.7) — extract detailed fields for prescriptions, lab results, allergies from NHC flat text. Unblocks P3.7 (current medications).
2. **Clinical Safety & Emergency** (D4.5) — red flag rules + emergency tagging + alerting. Requires doctor specialty knowledge input + ADR 0022 first.
3. **Active Notifications** (D6.6, P4.1, P4.2) — needs push infrastructure (WeChat template msg / web push / SMS). Stay passive for now.

---

## Doctor Workbench

### Core Communication & Chat

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D1.1 | AI助手对话 / AI Assistant Chat | **Done** | ChatPage.jsx — bubbles, markdown, file upload |
| D1.2 | 快速操作芯片 / Action Chips | **Done** | Quick commands (新增病历, 查询患者, 今日摘要) + ActionPanel (camera, gallery, file, patient) |
| D1.3 | 自然语言患者查询 / NL Patient Lookup | **Done** | PatientsPage detects NL queries via Chinese keyword detection |
| D1.4 | 对话式新建患者 / Conversational Patient Create | **Done** | Via chat + interview mode |
| D1.5 | 对话式创建任务 / Conversational Task Create | **Done** | Via chat + manual dialog |
| D1.6 | 临床摘要生成 / Clinical Summary | **Done** | Daily briefing + per-patient clinical summary via "总结{患者名}" chat command. Structured output: 基本信息→主要诊断→治疗经过→当前状态→注意事项 |
| D1.7 | 语音输入 / Voice Input | **Done** | VoiceInput.jsx — long-press mic, drag-to-cancel, Web Speech API (zh-CN) |
| D1.8 | 消息卡片与跳转 / Message Cards & Navigation | **Done** | DataCards render below AI replies: PatientCards, RecordCards, TaskCards with tap-to-navigate. Driven by existing HandlerResult.data (no backend changes). |

### Patient Management

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D2.1 | 患者列表 / Patient List | **Done** | PatientsPage — search, alphabetical groups, chief complaint |
| D2.2 | 新建患者 / Create Patient | **Done** | Chat-driven (no standalone form, which is fine) |
| D2.3 | 患者详情 / Patient Detail | **Done** | PatientDetail — info, records tabs, export, delete, chat |
| D2.4 | 患者搜索 / Patient Search | **Done** | Text + NL search |
| D2.5 | 患者状态指示 / Patient Status Indicator | **Done** | Triage color dots (red/yellow/green) in patient list based on latest message triage_category |
| D2.6 | 医生档案增强 / Doctor Profile Enhancement | **Done** | Name, specialty, clinic name, bio — all editable via SettingsPage. Avatar deferred (cosmetic). |

### Medical Records

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D3.1 | 病历结构化 / Record Structuring (14 fields) | **Done** | RecordFields.jsx — full 14-field NHC standard display |
| D3.2 | 病历导入（图片/PDF） / Record Import | **Done** | ChatPage + PatientsPage import flow (image, PDF, file) |
| D3.3 | 病历导出 (PDF) / Record Export | **Done** | ExportSelectorDialog — sections + range picker |
| D3.4 | 病历查看历史 / Visit History | **Done** | PatientDetail record tabs (time-ordered, filterable by type) |
| D3.5 | 处方记录 / Prescription Records | **Defer** | No dedicated prescription view; data in orders_followup flat text. Group: Structured Clinical Data |
| D3.6 | 检验报告 / Lab Results | **Defer** | `lab` record type exists but no structured lab display. Group: Structured Clinical Data |
| D3.7 | 过敏信息 / Allergy Information | **Defer** | Stored in allergy_history NHC field, no dedicated CRUD. Group: Structured Clinical Data |

### Diagnostic Assistance & Clinical Decision Support

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D4.1 | AI辅助诊断 / AI Diagnostic Assistance | **Done** | Full CDS pipeline + ReviewPage.jsx with trigger, polling, suggestion display |
| D4.2 | 鉴别诊断 / Differential Diagnosis | **Done** | SuggestionSection groups by `differential`; DiagnosisCard with confidence badges |
| D4.3 | 推荐检查 / Recommended Workup | **Done** | SuggestionSection groups by `workup`; urgency badges (常规/紧急/急诊) |
| D4.4 | 治疗建议 / Treatment Suggestions | **Done** | SuggestionSection groups by `treatment`; intervention badges (药物/手术/观察/转诊) |
| D4.5 | 危险信号检测 / Red Flag Detection | **Defer** | Backend returns red_flags in diagnosis; needs doctor-curated specialty rules + ADR 0022 knowledge base first. Group: Clinical Safety & Emergency |
| D4.6 | 诊断审核工作流 / Review Workflow | **Done** | ReviewPage.jsx — 5 decision states (pending/confirmed/rejected/edited/custom), inline edit, finalize. Route `/doctor/review/:recordId` active |
| D4.7 | 诊断原理和病例参考 / Case References | **Defer** | Similar case matching inline in review page. embedding.py removed — needs new lightweight approach (Ollama embeddings, LLM-based, or keyword matching) |
| D4.8 | 医学术语知识库 / Knowledge Base Management | **Done** | KnowledgeSubpage — view/add/delete items across 5 categories |
| D4.9 | 病例库管理 / Case History Management | **Cut** | Redundant — patient list + patient detail already serves as case library; D4.7 surfaces relevant cases inline |

### Task & Follow-up Management

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D5.1 | 任务系统 / Task Management | **Done** | TasksPage — filter chips, date groups, status actions, snooze |
| D5.2 | 任务创建 / Task Creation | **Done** | CreateTask dialog + chat-driven + auto from diagnosis |
| D5.3 | 任务提醒与通知 / Task Notifications | **Backend only** | Backend sends WeChat notifications via APScheduler; no doctor preference UI |
| D5.4 | 医生→患者消息回复 / Doctor Reply to Patient | **Done** | PatientDetail chat panel with `replyToPatient`; reply marks inbound as ai_handled + drafts as stale |
| D5.5 | 患者消息分类 / Patient Message Triage | **Done** | Triage color dots in patient list + PatientDetail; draft reply pipeline with cited_rules; undrafted message notice; no dedicated triage dashboard (handled inline) |

### Settings & Admin

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D6.1 | 我的二维码 / QR Code Generator | **Done** | QRDialog.jsx with `qrcode.react`; `generateQRToken` API; accessible from SettingsPage |
| D6.2 | 设置页面 / Settings Hub | **Done** | SettingsPage — profile, template, KB, QR code, about, logout |
| D6.3 | AI助手定制 / AI Assistant Customization | **Done** | Knowledge base IS the AI customization: single bucket, all items fed to all LLM calls, document upload with LLM processing, citation tracking. No separate "style settings" needed — doctors control AI behavior through knowledge items. |
| D6.4 | 文档上传与管理 / Document Upload & Management | **Done** | Upload PDF/DOCX/TXT → LLM processes → doctor previews → save. Citations via [KB-{id}] in diagnosis. 5 categories killed → single bucket. Dead embedding code removed. QA: 7/7 pass |
| D6.5 | 模板管理 / Template Management | **Done** | TemplateSubpage — upload custom outpatient report template (PDF/DOCX/TXT), delete/revert to default |
| D6.6 | 通知偏好设置 / Notification Preferences | **Defer** | No notification settings UI. Notifications stay passive until push infra built. Group: Active Notifications |
| D6.7 | 数据导出 / Data Export | **Done** | Per-patient PDF with section/range filtering + bulk ZIP export (all patients). Streaming generation, font caching, async polling. QA: 5/5 pass |

---

## Patient Portal

### Registration & Entry

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| P1.1 | QR码扫码入口 / QR Code Entry | **Done** | PatientPage absorbs URL params (`token`, `doctor_id`, `name`); doctor generates QR via D6.1; patient scans → auto-login/register |
| P1.2 | 患者自注册 / Patient Self-Registration | **Done** | LoginPage patient tab — select doctor, nickname, gender, passcode |
| P1.3 | 患者登录 / Patient Login | **Done** | Phone + passcode login with multi-role detection |

### Pre-Consultation Interview

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| P2.1 | AI引导预问诊采访 / AI-Guided Interview | **Done** | InterviewPage — 7 clinical fields, progress bar, session resume, suggestion chips |
| P2.2 | 患者预问诊确认预览 / Interview Review | **Done** | Confirm/cancel in interview with collected field summary |
| P2.3 | 语音输入 (患者端) / Voice Input (Patient) | **Done** | VoiceInput.jsx reused in patient InterviewPage + ChatTab. WeChat-style mic toggle left of input. QA: 6/6 pass |
| P2.4 | 文字输入 / Text Input | **Done** | Text input in interview + chat |
| P2.5 | 患者上传医疗文件 / Patient File Upload | **Done** | `patientUpload` API wired |
| P2.6 | 预问诊完成提交 / Interview Submission | **Done** | Confirm triggers draft record + doctor task + notification |

### Patient Portal Post-Visit

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| P3.1 | 患者病历查看 / View Medical Records | **Done** | RecordsTab in PatientPage with type filtering |
| P3.2 | 患者发消息给医生 / Send Message to Doctor | **Done** | ChatTab with `sendPatientChat` |
| P3.3 | 患者看医生回复 / Receive Doctor Replies | **Done** | Chat polling (10s visible, 60s hidden) shows doctor bubbles |
| P3.4 | 治疗计划可见性 / Treatment Plan Visibility | **Partial** | Patient TasksTab shows pending/completed task checklist (medications, follow-ups); no dedicated treatment plan view with medication schedule |
| P3.5 | 我的健康时间线 / Health Timeline | **Done** | RecordsTab — chronological timeline grouped by month, vertical line with colored type dots, clickable to record detail |
| P3.6 | 当前待办清单 / Patient To-Do List | **Done** | TasksTab — pending/completed split, checkbox, undo |
| P3.7 | 当前用药清单 / Current Medications | **Defer** | Blocked by D3.5 (structured prescription data). Group: Structured Clinical Data |
| P3.8 | 医生信息卡片 / Doctor Info Card | **Done** | ProfileTab — "我的医生" section with doctor name + specialty via NameAvatar |

### Patient Notifications

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| P4.1 | 患者通知能力 / Patient Notifications | **Defer** | Needs push infrastructure (WeChat template msg / web push / SMS). Group: Active Notifications |
| P4.2 | 患者复诊提醒 / Follow-up Reminders | **Defer** | Blocked by P4.1 push infra. Group: Active Notifications |

---

## Cross-Cutting

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| X1.1 | 统一认证系统 / Unified Auth | **Done** | LoginPage with doctor/patient tabs, multi-role detection, role picker |
| X1.2 | UI设计系统 / Design System | **Done** | MUI primary = green (#52C772), bubbles/bg/shadows/radius match spec. Minor: `COLOR.primary` blue (#1B6EF3) used as accent in some components — cosmetic, not a divergence |
| X1.3 | 底部标签栏 / Bottom Tab Bar | **Done** | Mobile bottom nav (4 tabs), desktop left sidebar (5 items + logout) |
| X1.4 | 推入式导航 / Push Navigation | **Done** | SubpageHeader with back button, state-driven push navigation |

---

## Dead/Disabled Frontend Code

| Component | File | Status |
|-----------|------|--------|
| DIAGNOSIS quick command | ChatPage constants | `disabled: true` — chat shortcut disabled (review page works independently) |
| inviteLogin | api.js | Legacy auth method, never called |
| unifiedMe | api.js | Token verify, never called |
| sendPatientMessage | api.js | Overlaps with sendPatientChat, never called |
| getPatientTimeline | api.js | Timeline endpoint defined but never called |

> **Removed from dead list (now active):** `getPatientMe` — called in PatientPage on mount.
> **Removed from dead list (deleted):** `DiagnosisSection.jsx`, `ReviewDetail.jsx`, `LabelPicker.jsx` — no longer exist in codebase.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-25 | Initial matrix: 30/61 done (49%) |
| 2026-03-27 | Verified against code. Diagnosis UI (D4.1-D4.4, D4.6) fully enabled. QR flow (D6.1, P1.1) implemented. Patient timeline (P3.5), doctor info card (P3.8) done. Triage color-coding (D5.5), knowledge-based AI customization (D6.3), treatment task checklist (P3.4) now partial. Item count corrected to 65. New score: 43/65 done (66%). Corrected NHC fields (not SOAP) |
| 2026-03-27 | Triaged 14 remaining items: **Build** 4 (P2.3, D6.7, D6.4, D4.7), **Defer** 9 in 3 groups (Structured Clinical Data, Clinical Safety & Emergency, Active Notifications), **Cut** 1 (D4.9 — redundant with patient list + D4.7) |
| 2026-03-27 | Implemented 3 build items: **P2.3** (patient voice input, QA 6/6), **D6.7** (bulk data export + single-patient section filtering, QA 5/5), **D6.4** (document upload + LLM processing + citation display + kill 5 categories + remove dead embedding code, QA 7/7). Score: 43→46 done (66%→71%). 1 build item remaining: D4.7 |
| 2026-03-28 | **D2.5** done (triage color dots in patient list), **D5.5** done (draft reply pipeline + cited_rules + undrafted notice). Teaching loop, KB source footer, file storage, demo sim engine, followup_reply prompt rewrite, tab badge fixes, session persistence fix. Score: 51→53 done (78%→82%) |
