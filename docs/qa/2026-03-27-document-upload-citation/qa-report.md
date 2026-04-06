# QA Report — D6.4 Document Upload + Citation

> Date: 2026-03-27
> Branch: main
> Target: http://localhost:5173 (dev server, mock data)
> Scope: Knowledge upload UI, category removal, citation wiring, dead code removal
> Tier: Standard (frontend-only, no backend server for upload/citation end-to-end)

## Summary

| Metric | Value |
|--------|-------|
| Pages tested | 3 (KnowledgeSubpage, AddKnowledge, ReviewPage) |
| Tests run | 7 |
| Passed | 7 |
| Failed | 0 |
| Bugs found | 0 |
| Console errors (new) | 0 |

## Test Results

### T1: Knowledge list — loads without category filter
- **Status:** PASS
- **Evidence:** `snapshots/10-knowledge-list.png`
- **Details:** Knowledge list loads with 11 items. No category filter chips visible. Items display with text and metadata.

### T2: Add knowledge — file upload section visible
- **Status:** PASS
- **Evidence:** `snapshots/11-add-knowledge.png`
- **Details:** "上传文件" section at top with description "支持 PDF、Word、TXT 文件，AI 会自动提取并整理内容". Upload button with file icon.

### T3: Add knowledge — text input section visible
- **Status:** PASS
- **Evidence:** `snapshots/11-add-knowledge.png`
- **Details:** "手动输入" section with text area. Placeholder: "用自然语言描述您的临床经验、诊断规则、问诊策略等". Helper: "用自然语言描述，AI 会在相关场景中参考".

### T4: Add knowledge — no category picker
- **Status:** PASS
- **Evidence:** `snapshots/11-add-knowledge.png`
- **Details:** Category picker completely removed. Only "上传文件" and "手动输入" sections with "或" divider between them.

### T5: Add knowledge — "或" divider between upload and text
- **Status:** PASS
- **Evidence:** `snapshots/11-add-knowledge.png`
- **Details:** Clear visual separation between the two input methods.

### T6: Review page — loads correctly
- **Status:** PASS
- **Evidence:** `snapshots/12-review-page.png`
- **Details:** "诊断审核" page loads with "请 AI 分析此病历" trigger button. Citation display is wired but requires real suggestions with [KB-{id}] markers to show chips.

### T7: Console health
- **Status:** PASS
- **Details:** Zero new JS errors. Only pre-existing @emotion/react duplicate warning.

## Limitations

- **File upload flow not end-to-end testable** — requires running backend with LLM to extract + process document. The upload button, preview dialog, and save flow are wired but can't be triggered without the real API.
- **Citation chips not testable** — requires real diagnosis suggestions containing [KB-{id}] markers. Mock data doesn't include citations. The parsing, chip rendering, and CitationSheet are wired but invisible with mock data.
- **Backend changes verified only via syntax check** — Python files pass py_compile but runtime behavior requires a live server + LLM.

## Backend Verification

| File | py_compile | Status |
|------|-----------|--------|
| `doctor_knowledge.py` | PASS | New functions + scoring changes |
| `knowledge_handlers.py` | PASS | 3 new endpoints |
| `prompt_config.py` | PASS | All categories → "all" |
| `prompt_composer.py` | PASS | Handles "all" sentinel |
| `main.py` | PASS | Embedding preload removed |

## Dead Code Removal Verified

| Item | Status |
|------|--------|
| `embedding.py` deleted | PASS |
| `main.py` preload removed | PASS |
| `requirements.txt` deps removed | PASS |
| `knowledge_ingest.md` prompt created | PASS (4503 bytes) |

## Screenshots

| File | Description |
|------|-------------|
| `snapshots/10-knowledge-list.png` | Knowledge list without category filters |
| `snapshots/11-add-knowledge.png` | Add page with upload + text input |
| `snapshots/12-review-page.png` | Review page (citation wiring ready) |
