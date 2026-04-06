# QA Report — D6.7 Bulk Data Export

> Date: 2026-03-27
> Branch: main
> Target: http://localhost:5173 (dev server, mock data)
> Scope: Settings bulk export button + Export selector dialog section wiring
> Tier: Standard (frontend-only, no backend server running)

## Summary

| Metric | Value |
|--------|-------|
| Pages tested | 2 (Settings, PatientDetail) |
| Tests run | 5 |
| Passed | 5 |
| Failed | 0 |
| Bugs found | 0 |
| Console errors (new) | 0 |

## Test Results

### T1: Settings — Bulk export button visible
- **Status:** PASS
- **Evidence:** `snapshots/07-settings-bulk-export.png`
- **Details:** "导出全部数据" row appears in 工具 section with download icon, subtitle "下载所有患者病历（ZIP）", and chevron. Positioned after 我的二维码.

### T2: Patient Detail — Export button accessible
- **Status:** PASS
- **Evidence:** `snapshots/08-patient-detail.png`
- **Details:** Patient detail page loads. Profile expands to reveal action bar with 导出PDF button.

### T3: Export Selector Dialog — Sections rendered
- **Status:** PASS
- **Evidence:** `snapshots/09-export-selector-dialog.png`
- **Details:** Dialog shows all 6 sections: 基本信息 (必选), 诊断信息, 就诊记录, 处方记录, 检验报告, 过敏信息. Each has a toggle checkbox. 就诊记录 has range selector (最近5次/最近10次/全部). 取消 and 生成PDF buttons at bottom.

### T4: Export Selector Dialog — Range selector
- **Status:** PASS
- **Evidence:** `snapshots/09-export-selector-dialog.png`
- **Details:** Three range options visible under 就诊记录: 最近5次, 最近10次, 全部. Clickable chip-style buttons.

### T5: Console health
- **Status:** PASS
- **Details:** Zero console errors during the entire session (Settings → Patients → PatientDetail → ExportDialog).

## Limitations

- **Bulk export flow not end-to-end testable** — requires running backend to handle POST /api/export/bulk. Mock API provider doesn't implement this endpoint. The button, confirm dialog, and polling UI are wired but can only be fully tested with a live backend.
- **Export PDF download not testable** — same reason, no backend to generate the PDF. The section/range params are now passed to the API call but the actual filtering requires backend.

## Screenshots

| File | Description |
|------|-------------|
| `snapshots/07-settings-bulk-export.png` | Settings page with 导出全部数据 row |
| `snapshots/08-patient-detail.png` | Patient detail with export button |
| `snapshots/09-export-selector-dialog.png` | Export selector dialog with all sections |
