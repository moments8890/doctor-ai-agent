# Workflow 16 — Template management

Ship gate for **报告模板** — the report template manager where doctors
upload, replace, or delete a custom outpatient medical record template.
The template shapes the format of every AI-generated report; changes
here must be reflected in subsequent exports.

This workflow targets `TemplateSubpage.jsx`, routed via
`/doctor/settings/template`.

**Area:** `src/pages/doctor/subpages/TemplateSubpage.jsx`, template API
(`GET /api/export/template/status?doctor_id=` for status,
`POST /api/export/template/upload` multipart form for upload,
`DELETE /api/export/template?doctor_id=` for delete —
see `frontend/web/src/api.js:345-374`), `useApi()` context
**Spec:** `frontend/web/tests/e2e/16-template.spec.ts`
**Estimated runtime:** ~3 min manual / ~20 s automated

---

## Scope

**In scope**

- Render page shell: `PageSkeleton` with title "报告模板", back arrow,
  "当前模板" section with `TemplateStatusCard`, "操作" section with
  `TemplateActions`.
- Default state (no custom template): status card shows "使用国家卫生部
  2010 年标准格式 ›" link; no "已自定义" badge; actions show "上传模板文件"
  only (no delete row).
- Standard format preview: tapping the link opens `SheetDialog` titled
  "门诊病历标准格式" with 14 numbered fields (科别 through 医嘱及随访);
  "知道了" dismisses.
- Upload: tapping "上传模板文件" triggers hidden `<input type="file">`
  (accepts `.pdf,.docx,.doc,.txt,image/jpeg,image/png,image/webp`);
  uploading shows "上传中…" spinner; success shows green `Alert`
  "模板已上传（filename）"; status card updates to "已上传自定义模板
  （N 字符）" with "已自定义" badge.
- Replace: once a template exists, the upload row label reads
  "替换模板文件"; same upload flow applies.
- Delete: "删除模板，恢复默认" row appears only when a template exists;
  tapping opens `ConfirmDialog` with title "删除模板", message "删除后将恢
  复国家卫生部 2010 年标准格式。", cancel="保留" LEFT grey,
  confirm="确认删除" RIGHT red; confirm triggers delete API and shows
  success `Alert` "模板已删除，将使用默认格式".
- Format hint text at bottom: "支持格式：PDF、DOCX、DOC、TXT、JPG、PNG，
  最大 1 MB。"
- Error handling: upload/delete failures show red `Alert` with error
  message.

**Out of scope**

- How the template affects actual PDF export output — tested in export
  workflow, not Playwright.
- File size / format validation on the backend — backend unit tests.
- Desktop two-pane layout — this plan covers mobile only.

---

## Pre-flight

Standard pre-flight. No seed needed — the spec starts from a clean
doctor (no template) and exercises upload/delete through the UI or
API seeding.

---

## Steps

### 1. Page shell (no template)

| # | Action | Verify |
|---|--------|--------|
| 1.1 | Navigate to `/doctor/settings/template` (directly, or via 设置 → 报告模板) | `PageSkeleton` header "报告模板"; back arrow top-left |
| 1.2 | Observe "当前模板" section | `SectionLabel` "当前模板" visible |
| 1.3 | Status card — no template state | Title "门诊病历报告模板"; subtitle link "使用国家卫生部 2010 年标准格式 ›" in blue; no "已自定义" badge |
| 1.4 | Observe "操作" section | `SectionLabel` "操作" visible |
| 1.5 | Actions — no template state | Single row "上传模板文件" with right arrow; no "删除模板，恢复默认" row |
| 1.6 | Format hint at bottom | Text "支持格式：PDF、DOCX、DOC、TXT、JPG、PNG，最大 1 MB。" visible |

### 2. Standard format preview

| # | Action | Verify |
|---|--------|--------|
| 2.1 | Tap "使用国家卫生部 2010 年标准格式 ›" link | `SheetDialog` opens titled "门诊病历标准格式" with subtitle "卫医政发〔2010〕11号《病历书写基本规范》" |
| 2.2 | Observe field list | 14 numbered fields visible: "1. 科别" through "14. 医嘱及随访", each with a description |
| 2.3 | Tap "知道了" | Dialog closes |

### 3. Upload template

| # | Action | Verify |
|---|--------|--------|
| 3.1 | Tap "上传模板文件" | File picker opens (hidden `<input type="file">` triggered) |
| 3.2 | Select a valid file (e.g. test.txt) | Row shows "上传中…" with `CircularProgress`; after completion, green `Alert` "模板已上传（test.txt）" appears |
| 3.3 | Status card updates | Subtitle changes to "已上传自定义模板（N 字符）"; green "已自定义" badge appears |
| 3.4 | Actions update | Upload row label changes to "替换模板文件"; new row "删除模板，恢复默认" appears below in red text |

### 4. Replace template

| # | Action | Verify |
|---|--------|--------|
| 4.1 | Tap "替换模板文件" | File picker opens |
| 4.2 | Select a different valid file | "上传中…" spinner; success `Alert` "模板已上传（new-file.txt）"; char count in status card may change |

### 5. Delete template

| # | Action | Verify |
|---|--------|--------|
| 5.1 | Tap "删除模板，恢复默认" | `ConfirmDialog` opens: title "删除模板"; message "删除后将恢复国家卫生部 2010 年标准格式。"; "保留" button LEFT grey; "确认删除" button RIGHT red |
| 5.2 | Tap "保留" | Dialog closes; template still present; "已自定义" badge remains |
| 5.3 | Tap "删除模板，恢复默认" again → "确认删除" | "删除中…" spinner; dialog closes; success `Alert` "模板已删除，将使用默认格式" |
| 5.4 | Status card reverts | Subtitle returns to "使用国家卫生部 2010 年标准格式 ›" link; "已自定义" badge gone |
| 5.5 | Actions revert | Delete row disappears; upload row label back to "上传模板文件" |

### 6. Navigation

| # | Action | Verify |
|---|--------|--------|
| 6.1 | Tap back arrow | Returns to `/doctor/settings`; settings list visible |
| 6.2 | From settings list, tap "报告模板" row | Navigates to `/doctor/settings/template` |

---

## Edge cases

- **Upload a file > 1 MB** — backend should return an error; the red
  `Alert` should display the error message. No crash.
- **Upload an unsupported file type** — the `accept` attribute on the
  input filters the picker, but if bypassed (e.g. drag-and-drop),
  backend rejects with an error.
- **Network failure during upload** — `catch` block fires; "上传中…"
  resets; red `Alert` shows error message.
- **Network failure during delete** — same pattern; "删除中…" resets;
  red `Alert` shows error.
- **Rapid double-tap on upload row** — only one file picker should open.
- **Alert dismiss** — tapping the close icon on the `Alert` clears the
  message (`onClose` calls `setMsg({ type: "", text: "" })`).
- **File input reset after upload** — `fileRef.current.value = ""` in
  `finally` ensures selecting the same file again triggers `onChange`.

---

## Known issues

No open bugs as of 2026-04-11.

---

## Failure modes & debug tips

- **Status card stuck on "加载中…"** — `getTemplateStatus` API call
  failed or never resolved. Check network tab for
  `GET /api/export/template/status?doctor_id=`.
- **Upload succeeds but status doesn't update** — `loadStatus()` is
  called after upload; verify it fires and returns `has_template: true`.
- **Delete row doesn't appear after upload** — `status.has_template`
  must be truthy for the delete row to render. Check API response shape.
- **"已自定义" badge wrong color** — should use `COLOR.successLight` bg
  + `COLOR.primary` text. Inspect the badge `Box` styles.
- **ConfirmDialog buttons swapped** — must be cancel="保留" LEFT,
  confirm="确认删除" RIGHT with `confirmTone="danger"`.
