# UI Checkpoint — 2026-03-21

Captured after: P1.5 doctor training surfaces, UI restructure, design system (TYPE/ICON tokens), URL-based routing.

## Doctor (Mobile 375x812)

| Page | Screenshot |
|---|---|
| 首页 (Home/Briefing) | ![](doctor-home-mobile.png) |
| 患者 (Patients) | ![](doctor-patients-mobile.png) |
| 任务 (Tasks) | ![](doctor-tasks-mobile.png) |
| 设置 (Settings) | ![](doctor-settings-mobile.png) |
| 知识库 (Knowledge Base) | ![](doctor-knowledge-mobile.png) |

## Doctor (Desktop 1280x720)

| Page | Screenshot |
|---|---|
| 首页 (Home/Briefing) | ![](doctor-home-desktop.png) |
| 患者 (Patients) | ![](doctor-patients-desktop.png) |
| 任务 (Tasks) | ![](doctor-tasks-desktop.png) |
| 设置 (Settings) | ![](doctor-settings-desktop.png) |
| 知识库 (Knowledge Base) | ![](doctor-knowledge-desktop.png) |

## Patient (Mobile 375x812)

| Page | Screenshot |
|---|---|
| 主页 (Home + Quick Actions) | ![](patient-home-mobile.png) |
| 病历 (Records) | ![](patient-records-mobile.png) |
| 任务 (Tasks) | ![](patient-tasks-mobile.png) |
| 设置 (Settings/Profile) | ![](patient-settings-mobile.png) |

## Login

| View | Screenshot |
|---|---|
| Mobile | ![](login-mobile.png) |
| Desktop | ![](login-desktop.png) |

## What's in this build

- 4-tab navigation: 首页/患者/任务/设置 (doctor), 主页/病历/任务/设置 (patient)
- Centralized TYPE (7 text levels) + ICON (8 icon levels) from theme.js
- URL-based subpage routing (survives refresh)
- Knowledge base: categorized accordion, add form, case library
- Patient interview with suggestion chips
- ListCard pattern across all list views
- PageSkeleton layout (desktop 3-column, mobile fullscreen)
- SubpageHeader for drill-down navigation
