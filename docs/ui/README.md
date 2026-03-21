# UI Checkpoints

Periodic snapshots of all web UI pages for reference during iteration.

## Checkpoints

| Date | Directory | Notes |
|---|---|---|
| 2026-03-21 | [checkpoint-2026-03-21/](checkpoint-2026-03-21/) | P1.5 + design system + URL routing |

## How to Recapture

Prerequisites:
- Backend running: `./cli.py start --provider groq`
- Frontend running: `cd frontend/web && npm run dev`
- gstack browse installed: `~/.claude/skills/gstack/browse/dist/browse`

### Step 0: Seed mock data

```bash
PYTHONPATH=src ENVIRONMENT=development python scripts/seed_ui_data.py
```

This creates test accounts + enough data to populate every page:
- 3 patients with structured records and tags
- Review queue items with completed AI diagnoses
- Tasks (pending + completed)
- Knowledge items across all 5 categories
- Confirmed case history with reference counts
- Interview session with conversation history

Safe to run multiple times — skips existing data.

### Steps

```bash
# 1. Create checkpoint directory
DATE=$(date +%Y-%m-%d)
mkdir -p docs/ui/checkpoint-${DATE}

# 2. Set browse alias
B=~/.claude/skills/gstack/browse/dist/browse

# 3. Login as doctor (mobile)
$B viewport 375x812
$B goto http://localhost:5173/login
# Fill: test_doctor / 1234, click login

# 4. Capture each doctor page
for route in \
  "/doctor" \
  "/doctor/patients" \
  "/doctor/patients/12" \
  "/doctor/tasks" \
  "/doctor/chat" \
  "/doctor/settings" \
  "/doctor/settings/template" \
  "/doctor/settings/knowledge" \
  "/doctor/settings/about" \
; do
  name=$(echo $route | sed 's#/doctor/##;s#/#-#g;s#^$#home#')
  $B goto "http://localhost:5173${route}"
  sleep 1
  $B screenshot "docs/ui/checkpoint-${DATE}/doctor-${name}-mobile.png"
  # Save HTML with mobile viewport wrapper
  raw=$($B js "document.documentElement.outerHTML")
  cat > "docs/ui/checkpoint-${DATE}/doctor-${name}.html" << EOF
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>html,body{margin:0;padding:0}body{width:375px;height:812px;border:1px solid #ddd;min-height:812px;overflow-x:hidden}</style>
</head>
${raw}
</html>
EOF
done

# 5. Desktop captures
$B viewport 1280x720
for route in "/doctor" "/doctor/patients" "/doctor/tasks" "/doctor/settings" "/doctor/settings/knowledge"; do
  name=$(echo $route | sed 's#/doctor/##;s#/#-#g;s#^$#home#')
  $B goto "http://localhost:5173${route}"
  sleep 1
  $B screenshot "docs/ui/checkpoint-${DATE}/doctor-${name}-desktop.png"
done

# 6. Login as patient
$B viewport 375x812
$B goto http://localhost:5173/login
# Switch to patient tab, fill: test_patient / 1234, click login

# 7. Capture patient pages
for route in "/patient/chat" "/patient/records" "/patient/tasks" "/patient/profile"; do
  name=$(echo $route | sed 's#/patient/##;s#/#-#g')
  $B goto "http://localhost:5173${route}"
  sleep 1
  $B screenshot "docs/ui/checkpoint-${DATE}/patient-${name}-mobile.png"
done

# 8. Commit
git add docs/ui/checkpoint-${DATE}/
git commit -m "docs: UI checkpoint ${DATE}"
```

### Test accounts

| Role | Username | Passcode |
|---|---|---|
| Doctor | test_doctor | 1234 |
| Patient | test_patient | 1234 |

### All routes to capture

**Doctor (mobile 375x812 + desktop 1280x720):**
- `/doctor` — 首页 (briefing)
- `/doctor/chat` — AI 助手
- `/doctor/patients` — 患者列表
- `/doctor/patients/:id` — 患者详情
- `/doctor/tasks` — 任务
- `/doctor/tasks/task/:id` — 任务详情
- `/doctor/tasks/review/:id` — 审核详情
- `/doctor/settings` — 设置
- `/doctor/settings/template` — 报告模板
- `/doctor/settings/knowledge` — 知识库
- `/doctor/settings/about` — 关于

**Note:** For review detail (`/doctor/tasks/review/:id`), capture 3 screenshots:
1. Top — structured fields + AI suggestion chips
2. Middle (scroll to ~800px) — case references + red flags + differentials
3. Bottom (scroll to end) — workup + treatment with ✓/✗ buttons + disclaimer

To scroll inside the content container:
```javascript
$B js "document.querySelectorAll('div').forEach(d => { if (getComputedStyle(d).overflowY === 'auto' && d.scrollHeight > d.clientHeight) d.scrollTo(0, 800); })"
```

**Patient (mobile 375x812 only):**
- `/patient/chat` — 主页
- `/patient/records` — 病历列表
- `/patient/records/:id` — 病历详情
- `/patient/records/interview` — 预问诊
- `/patient/tasks` — 任务
- `/patient/profile` — 设置
