# UI Checkpoint — 2026-03-21

Captured after: P1.5 doctor training surfaces, UI restructure, design system (TYPE/ICON tokens), URL-based routing.

Each file is a full HTML snapshot of the rendered page. Open in a browser to view.

## Doctor (Mobile 375x812)

| Page | Route | File |
|---|---|---|
| 首页 (Briefing) | `/doctor` | [doctor-home.html](doctor-home.html) |
| AI 助手 (Chat) | `/doctor/chat` | [doctor-chat.html](doctor-chat.html) |
| 患者列表 | `/doctor/patients` | [doctor-patients.html](doctor-patients.html) |
| 患者详情 | `/doctor/patients/12` | [doctor-patient-detail.html](doctor-patient-detail.html) |
| 任务 | `/doctor/tasks` | [doctor-tasks.html](doctor-tasks.html) |
| 设置 | `/doctor/settings` | [doctor-settings.html](doctor-settings.html) |
| 报告模板 | `/doctor/settings/template` | [doctor-settings-template.html](doctor-settings-template.html) |
| 知识库 | `/doctor/settings/knowledge` | [doctor-settings-knowledge.html](doctor-settings-knowledge.html) |
| 关于 | `/doctor/settings/about` | [doctor-settings-about.html](doctor-settings-about.html) |

## Doctor (Desktop 1280x720)

| Page | Route | File |
|---|---|---|
| 首页 | `/doctor` | [doctor-home-desktop.html](doctor-home-desktop.html) |
| 患者 | `/doctor/patients` | [doctor-patients-desktop.html](doctor-patients-desktop.html) |
| 任务 | `/doctor/tasks` | [doctor-tasks-desktop.html](doctor-tasks-desktop.html) |
| 设置 | `/doctor/settings` | [doctor-settings-desktop.html](doctor-settings-desktop.html) |
| 知识库 | `/doctor/settings/knowledge` | [doctor-knowledge-desktop.html](doctor-knowledge-desktop.html) |

## Patient (Mobile 375x812)

| Page | Route | File |
|---|---|---|
| 主页 (Chat + Quick Actions) | `/patient/chat` | [patient-home.html](patient-home.html) |
| 病历 | `/patient/records` | [patient-records.html](patient-records.html) |
| 任务 | `/patient/tasks` | [patient-tasks.html](patient-tasks.html) |
| 设置 | `/patient/profile` | [patient-settings.html](patient-settings.html) |

## Login

| View | Route | File |
|---|---|---|
| Mobile | `/login` | [login.html](login.html) |
| Desktop | `/login` | [login-desktop.html](login-desktop.html) |

## What's in this build

- 4-tab navigation: 首页/患者/任务/设置 (doctor), 主页/病历/任务/设置 (patient)
- Centralized TYPE (7 text levels) + ICON (8 icon levels) from theme.js
- URL-based subpage routing (survives refresh)
- Knowledge base: categorized accordion, add form, case library
- Patient interview with suggestion chips
- ListCard pattern across all list views
- PageSkeleton layout (desktop 3-column, mobile fullscreen)
- SubpageHeader for drill-down navigation
- DiagnosisSection with per-item confirm/reject in review flow
