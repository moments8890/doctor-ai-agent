# UI Checkpoint — 2026-03-21

Captured after: P1.5 doctor training surfaces, UI restructure, design system (TYPE/ICON tokens), URL-based routing.

**[Open interactive prototype →](index.html)** — navigate by clicking buttons inside the phone frame.

## Pages Captured

### Doctor (Mobile 375x812)

| Page | Route | File |
|---|---|---|
| 首页 (Briefing) | `/doctor` | [html](doctor-home.html) |
| AI 助手 (Chat) | `/doctor/chat` | [html](doctor-chat.html) |
| 患者列表 | `/doctor/patients` | [html](doctor-patients.html) |
| 患者详情 | `/doctor/patients/:id` | [html](doctor-patient-detail.html) |
| 新建患者 | `/doctor/patients/new` | [html](doctor-patients-new.html) |
| 任务 | `/doctor/tasks` | [html](doctor-tasks.html) |
| 任务详情 | `/doctor/tasks/task/:id` | [html](doctor-task-detail.html) |
| 新建任务 | `/doctor/tasks/new` | [html](doctor-tasks-new.html) |
| 审核详情 (inline AI建议) | `/doctor/tasks/review/:id` | [html](doctor-review-diagnosis.html) |
| 设置 | `/doctor/settings` | [html](doctor-settings.html) |
| 报告模板 | `/doctor/settings/template` | [html](doctor-settings-template.html) |
| 知识库 | `/doctor/settings/knowledge` | [html](doctor-settings-knowledge.html) |
| 新增知识 | `/doctor/settings/knowledge/new` | [html](doctor-knowledge-new.html) |
| 关于 | `/doctor/settings/about` | [html](doctor-settings-about.html) |

### Doctor (Desktop 1280x720)

| Page | Route | File |
|---|---|---|
| 首页 | `/doctor` | [html](doctor-home-desktop.html) |
| 患者 | `/doctor/patients` | [html](doctor-patients-desktop.html) |
| 任务 | `/doctor/tasks` | [html](doctor-tasks-desktop.html) |
| 设置 | `/doctor/settings` | [html](doctor-settings-desktop.html) |
| 知识库 | `/doctor/settings/knowledge` | [html](doctor-knowledge-desktop.html) |

### Patient (Mobile 375x812)

| Page | Route | File |
|---|---|---|
| 主页 (Chat + Quick Actions) | `/patient/chat` | [html](patient-home.html) |
| 病历列表 | `/patient/records` | [html](patient-records.html) |
| 病历详情 | `/patient/records/:id` | [html](patient-record-detail.html) |
| 预问诊 | `/patient/records/interview` | [html](patient-interview.html) |
| 任务 | `/patient/tasks` | [html](patient-tasks.html) |
| 设置 | `/patient/profile` | [html](patient-settings.html) |

### Login

| View | Route | File |
|---|---|---|
| Mobile | `/login` | [html](login.html) |
| Desktop | `/login` | [html](login-desktop.html) |

## File structure

- `index.html` — interactive prototype with phone frame (navigate via in-page clicks)
- `{name}.html` — standalone page with centered phone frame
- `{name}_raw.html` — raw DOM snapshot (the actual captured HTML)

## What's in this build

- 4-tab navigation: 首页/患者/任务/设置 (doctor), 主页/病历/任务/设置 (patient)
- Centralized TYPE (7 text levels) + ICON (8 icon levels) from theme.js
- URL-based subpage routing (survives refresh)
- Inline AI suggestion chips in review detail (辅助检查/初步诊断/治疗方案/医嘱及随访)
- Knowledge base: categorized accordion, add form, case library
- Patient interview with suggestion chips
- ListCard pattern across all list views
- PageSkeleton layout (desktop 3-column, mobile fullscreen)
