# Feature Parity Matrix — Frontend vs. Product Requirements

> Date: 2026-03-25
> Method: Product docs (strategy, requirements, CDS design, UX spec) cross-referenced against actual frontend code
> Scope: All user-facing features across doctor workbench, patient portal, admin, and cross-cutting

## Summary Scorecard

| Category | Done | Partial | Backend Only | Missing | Total |
|----------|------|---------|-------------|---------|-------|
| **Doctor Workbench** | 18 | 4 | 4 | 14 | 40 |
| **Patient Portal** | 9 | 0 | 0 | 8 | 17 |
| **Cross-Cutting** | 3 | 1 | 0 | 0 | 4 |
| **Total** | **30** | **5** | **4** | **22** | **61** |

**49% feature complete** (30/61 done), 57% including partials.

---

## Top 5 Gaps by Impact

1. **Diagnosis UI completely disabled** — Backend CDS pipeline works (D4.1-D4.4), but `ReviewDetail.jsx` returns `null` and `DiagnosisSection` isn't rendered. Doctor's #1 ask: "希望能够有初步的诊断".
2. **Patient notifications = zero** — Patients can't receive any push. Follow-up reminders, appointment alerts, medication reminders all missing.
3. **QR code entry** — No way for patients to scan and self-register. The intended primary entry point doesn't exist.
4. **Design system mostly aligned** — MUI primary is green (#52C772), bg/shadows/radius match spec. Minor: `COLOR.primary` blue (#1B6EF3) used as accent in some components alongside the green.
5. **Clinical data views** — No structured views for prescriptions, lab results, allergies. Records are flat text.

---

## Doctor Workbench

### Core Communication & Chat

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D1.1 | AI助手对话 / AI Assistant Chat | **Done** | ChatSection.jsx — bubbles, markdown, file upload |
| D1.2 | 快速操作芯片 / Action Chips | **Done** | Quick commands (新增病历, 查询患者, 今日摘要) + ActionPanel (camera, gallery, file, patient) |
| D1.3 | 自然语言患者查询 / NL Patient Lookup | **Done** | PatientsSection detects NL queries via Chinese keyword detection |
| D1.4 | 对话式新建患者 / Conversational Patient Create | **Done** | Via chat + interview mode |
| D1.5 | 对话式创建任务 / Conversational Task Create | **Done** | Via chat + manual dialog |
| D1.6 | 临床摘要生成 / Clinical Summary | **Partial** | Daily briefing exists, per-patient "总结最近三次就诊" unclear |
| D1.7 | 语音输入 / Voice Input | **Done** | VoiceInput.jsx — long-press mic, drag-to-cancel |
| D1.8 | 消息卡片与跳转 / Message Cards & Navigation | **Partial** | Chat renders markdown, no structured clickable cards with deep-link navigation |

### Patient Management

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D2.1 | 患者列表 / Patient List | **Done** | PatientsSection — search, alphabetical groups, chief complaint |
| D2.2 | 新建患者 / Create Patient | **Done** | Chat-driven (no standalone form, which is fine) |
| D2.3 | 患者详情 / Patient Detail | **Done** | PatientDetail — info, records tabs, export, delete |
| D2.4 | 患者搜索 / Patient Search | **Done** | Text + NL search |
| D2.5 | 患者状态指示 / Patient Status Indicator | **Missing** | No risk badges (red/orange/none) in patient list |
| D2.6 | 医生档案增强 / Doctor Profile Enhancement | **Partial** | Name + specialty only, no avatar/clinic/bio/hours |

### Medical Records

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D3.1 | 病历结构化 / Record Structuring (14 fields) | **Done** | RecordFields.jsx — full 14-field SOAP display |
| D3.2 | 病历导入（图片/PDF） / Record Import | **Done** | ChatSection + PatientsSection import flow |
| D3.3 | 病历导出 (PDF) / Record Export | **Done** | ExportSelectorDialog — sections + range picker |
| D3.4 | 病历查看历史 / Visit History | **Done** | PatientDetail record tabs (time-ordered) |
| D3.5 | 处方记录 / Prescription Records | **Missing** | No dedicated prescription view |
| D3.6 | 检验报告 / Lab Results | **Missing** | Records have lab type but no structured lab display |
| D3.7 | 过敏信息 / Allergy Information | **Missing** | No allergy CRUD |

### Diagnostic Assistance & Clinical Decision Support

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D4.1 | AI辅助诊断 / AI Diagnostic Assistance | **Backend only** | CDS pipeline generates diagnosis, frontend `DiagnosisSection` not rendered |
| D4.2 | 鉴别诊断 / Differential Diagnosis | **Backend only** | Backend generates 3-5 alternatives, no frontend display |
| D4.3 | 推荐检查 / Recommended Workup | **Backend only** | Backend generates, no frontend display |
| D4.4 | 治疗建议 / Treatment Suggestions | **Backend only** | Backend generates drug classes, no frontend display |
| D4.5 | 危险信号检测 / Red Flag Detection | **Missing** | No red flag alert banner UI |
| D4.6 | 诊断审核工作流 / Review Workflow | **Disabled** | `ReviewDetail.jsx` returns `null` — fully disabled |
| D4.7 | 诊断原理和病例参考 / Case References | **Missing** | No matched-cases display |
| D4.8 | 医学术语知识库 / Knowledge Base Management | **Done** | SettingsSection — view/add/delete knowledge items |
| D4.9 | 病例库管理 / Case History Management | **Missing** | No case library UI |

### Task & Follow-up Management

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D5.1 | 任务系统 / Task Management | **Done** | TasksSection — filter chips, date groups, status actions |
| D5.2 | 任务创建 / Task Creation | **Done** | CreateTask dialog + chat-driven |
| D5.3 | 任务提醒与通知 / Task Notifications | **Backend only** | Backend sends WeChat notifications, no preference UI |
| D5.4 | 医生→患者消息回复 / Doctor Reply to Patient | **Done** | PatientDetail chat panel with `replyToPatient` |
| D5.5 | 患者消息分类 / Patient Message Triage | **Missing** | No urgency color-coding or triage dashboard |

### Settings & Admin

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| D6.1 | 我的二维码 / QR Code Generator | **Missing** | No QR endpoint or UI |
| D6.2 | 设置页面 / Settings Hub | **Done** | SettingsSection — profile, template, KB, logout |
| D6.3 | AI助手定制 / AI Assistant Customization | **Missing** | No AI behavior/style preference UI |
| D6.4 | 文档上传与管理 / Document Upload & Management | **Missing** | No clinical guidelines upload |
| D6.5 | 模板管理 / Template Management | **Done** | PDF template upload/delete (PDF only) |
| D6.6 | 通知偏好设置 / Notification Preferences | **Missing** | No notification settings UI |
| D6.7 | 数据导出 / Data Export | **Missing** | No bulk backup/export UI |

---

## Patient Portal

### Registration & Entry

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| P1.1 | QR码扫码入口 / QR Code Entry | **Missing** | No QR flow — intended primary patient entry |
| P1.2 | 患者自注册 / Patient Self-Registration | **Done** | PatientPage login/register with phone + YOB |
| P1.3 | 患者登录 / Patient Login | **Done** | Phone + YOB login |

### Pre-Consultation Interview

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| P2.1 | AI引导预问诊采访 / AI-Guided Interview | **Done** | InterviewFlow — 14 fields, progress bar, session resume |
| P2.2 | 患者预问诊确认预览 / Interview Review | **Done** | Confirm/cancel in interview |
| P2.3 | 语音输入 (患者端) / Voice Input (Patient) | **Missing** | No voice in patient portal |
| P2.4 | 文字输入 / Text Input | **Done** | Text input in interview |
| P2.5 | 患者上传医疗文件 / Patient File Upload | **Done** | `patientUpload` API wired |
| P2.6 | 预问诊完成提交 / Interview Submission | **Done** | Confirm triggers task + record creation |

### Patient Portal Post-Visit

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| P3.1 | 患者病历查看 / View Medical Records | **Done** | RecordsTab in PatientPage |
| P3.2 | 患者发消息给医生 / Send Message to Doctor | **Done** | ChatTab with `sendPatientChat` |
| P3.3 | 患者看医生回复 / Receive Doctor Replies | **Done** | Chat polling shows doctor bubbles |
| P3.4 | 治疗计划可见性 / Treatment Plan Visibility | **Missing** | No treatment plan checklist view |
| P3.5 | 我的健康时间线 / Health Timeline | **Missing** | No chronological timeline UI |
| P3.6 | 当前待办清单 / Patient To-Do List | **Done** | TasksTab in PatientPage |
| P3.7 | 当前用药清单 / Current Medications | **Missing** | No medication list view |
| P3.8 | 医生信息卡片 / Doctor Info Card | **Missing** | No doctor profile display in portal |

### Patient Notifications

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| P4.1 | 患者通知能力 / Patient Notifications | **Missing** | Zero patient notification implementation |
| P4.2 | 患者复诊提醒 / Follow-up Reminders | **Missing** | No multi-stage patient reminders |

---

## Cross-Cutting

| ID | Feature | Status | Notes |
|----|---------|--------|-------|
| X1.1 | 统一认证系统 / Unified Auth | **Done** | LoginPage with role tabs |
| X1.2 | UI设计系统 / Design System | **Mostly aligned** | MUI primary = green (#52C772, close to spec #07C160), bubbles/bg/shadows/radius all match spec. `COLOR.primary` blue (#1B6EF3) used as accent in some components — minor inconsistency, not a divergence |
| X1.3 | 底部标签栏 / Bottom Tab Bar | **Done** | Mobile bottom nav, desktop sidebar |
| X1.4 | 推入式导航 / Push Navigation | **Done** | SubpageHeader with back button |

---

## Dead/Disabled Frontend Code

| Component | File | Status |
|-----------|------|--------|
| DiagnosisSection | `pages/doctor/DiagnosisSection.jsx` | Not rendered — diagnosis UI disabled |
| ReviewDetail | `pages/doctor/ReviewDetail.jsx` | Returns `null` — review workflow removed |
| DIAGNOSIS action | ChatSection quick commands | Marked disabled in constants |
| LabelPicker | `pages/doctor/LabelPicker.jsx` | Renders but no backend persistence |
| inviteLogin | api.js | Legacy auth, never called |
| unifiedMe | api.js | Token verify, never called |
| sendPatientMessage | api.js | Overlaps with sendPatientChat, never called |
| getPatientMe | api.js | Patient profile, never called |
| getPatientTimeline | api.js | Timeline endpoint, never called |
