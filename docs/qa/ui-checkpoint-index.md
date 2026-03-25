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
PYTHONPATH=src ENVIRONMENT=development python scripts/seed_ui_data.py --doctor-id=inv_hh_Y7p5cGJ0J --reset
```

This creates test accounts + enough data to populate every page:
- Doctor: 张三 (neurosurgery)
- 5 patients (周海涛, 吴晓燕, 孙国庆, 何丽萍, 马文斌) with structured records
- Review queue items (pending + reviewed) with AI diagnoses
- Doctor tasks (5) + patient-facing tasks (3)
- Knowledge items across all 5 categories
- Confirmed case history with reference counts
- Interview session with conversation history

### Step 1: Get IDs from seeded data

```bash
ENVIRONMENT=development PYTHONPATH=src python -c "
import asyncio
from db.engine import AsyncSessionLocal
from sqlalchemy import text
async def main():
    async with AsyncSessionLocal() as db:
        # All patients
        rows = await db.execute(text(\"SELECT id, name FROM patients WHERE doctor_id='inv_hh_Y7p5cGJ0J'\"))
        pids = []
        for r in rows:
            pids.append(str(r[0]))
            print(f'# patient {r[0]}: {r[1]}')
        print(f'PATIENT_IDS=({\" \".join(pids)})')
        # All reviews
        rows = await db.execute(text(\"SELECT id, patient_id, status FROM review_queue WHERE doctor_id='inv_hh_Y7p5cGJ0J'\"))
        rids = []
        for r in rows:
            rids.append(str(r[0]))
            print(f'# review {r[0]}: patient={r[1]} {r[2]}')
        print(f'REVIEW_IDS=({\" \".join(rids)})')
        # All tasks
        rows = await db.execute(text(\"SELECT id, title, status FROM doctor_tasks WHERE doctor_id='inv_hh_Y7p5cGJ0J'\"))
        tids = []
        for r in rows:
            tids.append(str(r[0]))
            print(f'# task {r[0]}: {r[1]} [{r[2]}]')
        print(f'TASK_IDS=({\" \".join(tids)})')
        # Knowledge items
        rows = await db.execute(text(\"SELECT id, category FROM doctor_knowledge_items WHERE doctor_id='inv_hh_Y7p5cGJ0J'\"))
        kids = []
        for r in rows:
            kids.append(str(r[0]))
            print(f'# knowledge {r[0]}: {r[1]}')
        print(f'KNOWLEDGE_IDS=({\" \".join(kids)})')
        # First record for patient detail
        rows = await db.execute(text(\"SELECT id FROM medical_records WHERE patient_id=(SELECT id FROM patients WHERE doctor_id='inv_hh_Y7p5cGJ0J' LIMIT 1) LIMIT 1\"))
        print(f'RECORD_ID={rows.first()[0]}')
asyncio.run(main())
"
```

Copy the printed array lines and run them to set the variables.

### Step 2: Capture

```bash
DATE=$(date +%Y-%m-%d)
DIR=docs/ui/checkpoint-${DATE}
mkdir -p "$DIR"
B=~/.claude/skills/gstack/browse/dist/browse

# ── Helper: save raw HTML ──
capture() {
  local route=$1 name=$2
  $B goto "http://localhost:5173${route}"
  sleep 1.5
  $B js "document.documentElement.outerHTML" > "${DIR}/${name}_raw.html"
  echo "  captured: ${name}"
}

# ── Helper: generate wrapped standalone page from raw ──
wrap_all() {
  for rawfile in "$DIR"/*_raw.html; do
    local name=$(basename "$rawfile" _raw.html)
    case "$name" in *desktop*) continue;; esac
    cat > "${DIR}/${name}.html" << 'WRAP_TOP'
<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
html,body{margin:0;padding:0;background:#f0f0f0;display:flex;justify-content:center;min-height:100vh}
.phone{width:375px;height:812px;background:#fff;overflow-y:auto;overflow-x:hidden;border:1px solid #ccc;margin:20px 0;box-shadow:0 4px 20px rgba(0,0,0,.1);border-radius:16px;position:relative}
</style></head><body><div class="phone">
WRAP_TOP
    cat "$rawfile" >> "${DIR}/${name}.html"
    cat >> "${DIR}/${name}.html" << 'WRAP_BOTTOM'
</div>
<script>
document.querySelectorAll('.phone *').forEach(el=>{
  if(getComputedStyle(el).position==='fixed'){el.style.position='absolute';el.style.width='375px';el.style.left='0';el.style.right='auto'}
});
</script></body></html>
WRAP_BOTTOM
  done
}

# ── Login as doctor ──
$B viewport 375x812
$B goto http://localhost:5173/login
# Fill: 张三 / 1234, click login
# (use $B snapshot -i to find refs, $B fill / $B click)

# ── Doctor list + new pages ──
capture "/doctor"                        "doctor-home"
capture "/doctor/chat"                   "doctor-chat"
capture "/doctor/patients"               "doctor-patients"
capture "/doctor/patients/new"           "doctor-patients-new"
capture "/doctor/tasks"                  "doctor-tasks"
capture "/doctor/tasks/new"              "doctor-tasks-new"
capture "/doctor/settings"               "doctor-settings"
capture "/doctor/settings/template"      "doctor-settings-template"
capture "/doctor/settings/knowledge"     "doctor-settings-knowledge"
capture "/doctor/settings/knowledge/new" "doctor-knowledge-new"
capture "/doctor/settings/about"         "doctor-settings-about"

# ── Doctor detail pages (all patients, reviews, tasks, knowledge) ──
for pid in "${PATIENT_IDS[@]}"; do
  capture "/doctor/patients/${pid}" "doctor-patient-${pid}"
done
for rid in "${REVIEW_IDS[@]}"; do
  capture "/doctor/tasks/review/${rid}" "doctor-review-${rid}"
done
for tid in "${TASK_IDS[@]}"; do
  capture "/doctor/tasks/task/${tid}" "doctor-task-${tid}"
done
for kid in "${KNOWLEDGE_IDS[@]}"; do
  capture "/doctor/settings/knowledge/${kid}" "doctor-knowledge-${kid}"
done

# ── Knowledge with expanded category ──
# Navigate to knowledge list, click first category to expand, then capture
# $B goto .../knowledge → $B click @e1 → capture as doctor-knowledge-expanded

# ── Doctor desktop pages (5) ──
$B viewport 1280x720
for route_name in \
  "/doctor:doctor-home-desktop" \
  "/doctor/patients:doctor-patients-desktop" \
  "/doctor/tasks:doctor-tasks-desktop" \
  "/doctor/settings:doctor-settings-desktop" \
  "/doctor/settings/knowledge:doctor-knowledge-desktop" \
; do
  route="${route_name%%:*}"
  name="${route_name##*:}"
  $B goto "http://localhost:5173${route}"
  sleep 1
  $B js "document.documentElement.outerHTML" > "${DIR}/${name}.html"
done

# ── Register + login as patient ──
$B viewport 375x812
# Register patient first (needed once after seed)
curl -s http://localhost:8000/api/auth/unified/register/patient -X POST \
  -H 'Content-Type: application/json' \
  -d '{"phone":"周海涛","name":"周海涛","year_of_birth":1971,"doctor_id":"inv_hh_Y7p5cGJ0J","gender":"male"}'
$B goto http://localhost:5173/login
# Switch to patient tab, fill: 周海涛 / 1971, click login

# ── Patient mobile pages (6) ──
capture "/patient/chat"               "patient-home"
capture "/patient/records"            "patient-records"
capture "/patient/records/${RECORD_ID}" "patient-record-detail"
capture "/patient/records/interview"  "patient-interview"
capture "/patient/tasks"              "patient-tasks"
capture "/patient/profile"            "patient-settings"

# ── Login page ──
$B js "localStorage.clear()"
$B goto http://localhost:5173/login
sleep 1
$B js "document.documentElement.outerHTML" > "${DIR}/login_raw.html"
$B viewport 1280x720
$B goto http://localhost:5173/login
sleep 1
$B js "document.documentElement.outerHTML" > "${DIR}/login-desktop.html"

# ── Generate wrapped .html files ──
wrap_all

# ── Commit ──
git add docs/ui/checkpoint-${DATE}/
git commit -m "docs: UI checkpoint ${DATE}"
```

### Test accounts

| Role | Username | Passcode |
|---|---|---|
| Doctor | 张三 | 1234 |
| Patient (周海涛) | 周海涛 | 1971 |

### All routes to capture

**Doctor list + new pages (11):**
- `/doctor` — 首页
- `/doctor/chat` — AI 助手
- `/doctor/patients` — 患者列表
- `/doctor/patients/new` — 新建患者
- `/doctor/tasks` — 任务
- `/doctor/tasks/new` — 新建任务
- `/doctor/settings` — 设置
- `/doctor/settings/template` — 报告模板
- `/doctor/settings/knowledge` — 知识库
- `/doctor/settings/knowledge/new` — 新增知识
- `/doctor/settings/about` — 关于

**Doctor detail pages (all seeded items):**
- `/doctor/patients/:id` — 每个患者的详情 (file: `doctor-patient-{id}`)
- `/doctor/tasks/task/:id` — 每个任务的详情 (file: `doctor-task-{id}`)
- `/doctor/tasks/review/:id` — 每个审核的详情 (file: `doctor-review-{id}`)
- `/doctor/settings/knowledge/:id` — 每个知识的详情 (file: `doctor-knowledge-{id}`)
- 知识库展开视图 (file: `doctor-knowledge-expanded`)

**Doctor desktop (5):**
- `/doctor`, `/doctor/patients`, `/doctor/tasks`, `/doctor/settings`, `/doctor/settings/knowledge`

**Patient (mobile only, 6):**
- `/patient/chat` — 主页 (chat + quick actions)
- `/patient/records` — 病历列表
- `/patient/records/:id` — 病历详情
- `/patient/records/interview` — 预问诊
- `/patient/tasks` — 任务 (3 patient-facing tasks seeded for 周海涛)
- `/patient/profile` — 设置

**Login:**
- `/login` — 登录 (mobile + desktop)
