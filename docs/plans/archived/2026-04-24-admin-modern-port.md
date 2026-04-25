# Admin Modern Port (v3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the existing dev-targeted admin (`frontend/web/src/pages/admin/`) to a modern operations console for non-dev viewers (e.g. hospital partner doctors), implementing the v3 mockup verbatim.

**Architecture:** New JSX surface mounted at `/admin?v=3` while v1 stays at `/admin` (default). Backend endpoints reused; only `运营` module and viewer-role auth are new. Cutover happens when v3 e2e tests pass.

**Tech stack:** React 18, react-router-dom v6, MUI (existing), `@mui/icons-material`, Material Symbols web font (already loaded in v3 mockup), FastAPI backend, Playwright e2e.

**Visual contract:** `docs/specs/2026-04-24-admin-modern-mockup-v3.html` — every visual decision (color, spacing, typography, motif) is locked in this file. When in doubt, open it side-by-side with the JSX you're writing.

**Existing backend endpoints (REUSE — do not duplicate):**
- `GET /api/admin/overview`, `/api/admin/doctors`, `/api/admin/activity`
- `GET /api/admin/doctors/{id}`, `/patients`, `/timeline`, `/related`
- `GET /api/admin/patients/{id}/related`
- `GET /api/admin/invites` (in `invite_handlers.py:45`)
- Auth: `X-Admin-Token` header → `require_admin_token(x_admin_token, env_name="UI_ADMIN_TOKEN")` in `src/channels/web/doctor_dashboard/deps.py:18`

**New backend additions (small):**
- `UI_ADMIN_VIEWER_TOKEN` env var → second valid token, read-only scope
- `GET /api/admin/ops/pilot-progress` — derives from existing data
- `GET /api/admin/ops/partner-report` — weekly snapshot, derives from existing data

**Phase structure (16 tasks, ship-behind-a-flag):**
- Phase 1: tokens + dual-mount shell (3 tasks) — v3 reachable, v1 untouched
- Phase 2: doctor detail rebuild (5 tasks) — 4 tabs, all components from mockup
- Phase 3: 运营 module (3 tasks) — invite codes, pilot progress, partner report
- Phase 4: permissions + polish (3 tasks) — viewer role, dev toggle, states+mobile
- Phase 5: cutover (2 tasks) — e2e tests pass, default route switches

**Test policy:** Logic-heavy code (filter reducers, viewer permission, decision-card data shaping) gets Vitest. Visual components get Playwright e2e against the running dev server (`frontend/web && npx playwright test`). The mockup is the visual oracle.

---

## Phase 1 — Tokens + dual-mount shell

### Task 1.1: Theme tokens file

**Files:**
- Create: `frontend/web/src/pages/admin/v3/tokens.js`

**Why:** Centralize the v3 design tokens so every component imports from one place. Mirrors the `:root { --bg-page; … }` block in the mockup.

- [ ] **Step 1: Create tokens module**

```js
// frontend/web/src/pages/admin/v3/tokens.js
// Design tokens for admin v3 — see docs/specs/2026-04-24-admin-modern-mockup-v3.html
// Theme proposal author: codex (consult mode, 2026-04-24).

export const COLOR = {
  bgPage:       "#F5F7F8",
  bgCanvas:     "#EEF2F3",
  bgCard:       "#FFFFFF",
  bgCardAlt:    "#FAFBFB",

  borderSubtle:  "#E9EEF0",
  borderDefault: "#DDE4E7",
  borderStrong:  "#C6D0D5",

  text1: "#1A1A1A",
  text2: "#5F6B76",
  text3: "#8B98A5",
  text4: "#B0BAC2",

  brand:       "#07C160",   // mobile primary; used sparingly per codex
  brandHover:  "#06AD56",
  brandTint:   "#E7F8EE",

  info:      "#576B95",     // AI surfaces, secondary emphasis
  infoTint:  "#EEF1F6",

  danger:       "#FA5151",
  dangerTint:   "#FFF1F1",
  dangerStrong: "#E03A3A",

  warning:     "#B07A1C",   // text-on-white variant of mobile #FFC300
  warningBg:   "#FFC300",
  warningTint: "#FFF8E0",
};

export const FONT = {
  // body=14px per codex density spec
  xs:   11,
  sm:   12,
  base: 13,
  body: 14,
  md:   15,
  lg:   17,
  xl:   22,
};

export const RADIUS = { sm: 6, md: 8, lg: 12, pill: 999 };

export const SPACE = {
  control:    36,   // button / nav-item / search height
  cardPad:    16,
  pageGutter: 20,
  sectionGap: 16,
};

export const SHADOW = {
  s1: "0 1px 1px rgba(15, 23, 28, 0.04)",
  s2: "0 1px 2px rgba(15, 23, 28, 0.05), 0 6px 16px -8px rgba(15, 23, 28, 0.06)",
};

export const FONT_STACK = {
  sans:
    '"PingFang SC","Noto Sans SC","HarmonyOS Sans SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
  mono:
    '"SF Mono","JetBrains Mono","Roboto Mono",ui-monospace,Menlo,monospace',
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/pages/admin/v3/tokens.js
git commit -m "feat(admin-v3): add design tokens (codex theme)"
```

---

### Task 1.2: Dual-mount shell + sidebar + topbar

**Files:**
- Create: `frontend/web/src/pages/admin/v3/AdminShellV3.jsx`
- Create: `frontend/web/src/pages/admin/v3/AdminSidebar.jsx`
- Create: `frontend/web/src/pages/admin/v3/AdminTopbar.jsx`
- Create: `frontend/web/src/pages/admin/v3/index.jsx` (entry; reads `?v=3` from URL)
- Modify: `frontend/web/src/pages/admin/AdminPage.jsx` — at the top of `AdminPage()`, branch on `useSearchParams().get("v") === "3"` and render `AdminPageV3` instead of the existing dashboard

**Why:** Mount v3 alongside v1 so we can preview without breaking anything. The query-param toggle is intentional (no env var, no build flag) — it lets the partner doctor be sent a single URL like `/admin?v=3` for the demo.

- [ ] **Step 1: Implement `AdminShellV3` shell**

```jsx
// frontend/web/src/pages/admin/v3/AdminShellV3.jsx
import { COLOR, FONT_STACK } from "./tokens";
import AdminSidebar from "./AdminSidebar";
import AdminTopbar from "./AdminTopbar";

export default function AdminShellV3({ section, breadcrumb, children }) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "240px 1fr",
      minHeight: "100vh",
      background: COLOR.bgPage,
      color: COLOR.text1,
      fontFamily: FONT_STACK.sans,
      fontSize: 14,
      lineHeight: 1.55,
      WebkitFontSmoothing: "antialiased",
    }}>
      <AdminSidebar activeSection={section} />
      <main style={{ minWidth: 0 }}>
        <AdminTopbar breadcrumb={breadcrumb} />
        <div style={{ padding: "20px 24px 80px", maxWidth: 1320 }}>
          {children}
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Implement `AdminSidebar`**

Read the mockup `<aside class="sidebar">` block to copy: brand row, three nav-groups (概览 / 运营 / 系统), user-menu at bottom. Use `Material Symbols Outlined` icon names from the mockup (`dashboard`, `stethoscope`, `groups`, `forum`, `network_intelligence`, `key`, `deployed_code_history`, `summarize`, `download`, `monitor_heart`, `history`).

Sidebar item active state = brand-tinted bg + 2px left rail (`::before` with `width: 2px; background: COLOR.brand; left: -12px`). The motif is the rail.

User-menu popover stays closed by default; opens on click. Hide for now — task 4.2 wires the dev-mode toggle.

- [ ] **Step 3: Implement `AdminTopbar`**

Mockup `<header class="topbar">`: 56px height, sticky, breadcrumb on left, search input + notification bell on right. Search is non-functional in this task (just a styled input that opens nothing).

The breadcrumb's `.here` span gets `fontSize: 22, fontWeight: 600, letterSpacing: "-0.015em"` — the *only* element in v3 that's bigger than 17px sans.

- [ ] **Step 4: Wire dual-mount in `AdminPage.jsx`**

```jsx
// in frontend/web/src/pages/admin/AdminPage.jsx, top of the file:
import AdminPageV3 from "./v3";

export default function AdminPage() {
  // read ?v=3 from URL — if present, mount v3 instead of legacy
  if (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("v") === "3") {
    return <AdminPageV3 />;
  }
  // ... existing AdminPage body unchanged
}
```

- [ ] **Step 5: Implement v3 index entry**

```jsx
// frontend/web/src/pages/admin/v3/index.jsx
import AdminShellV3 from "./AdminShellV3";

export default function AdminPageV3() {
  return (
    <AdminShellV3 section="doctors" breadcrumb={[{ label: "医生" }, { label: "选择医生", here: true }]}>
      <div style={{ color: "#5F6B76", fontSize: 14 }}>
        请从左侧选择医生（doctor detail 由 Task 2.x 实现）
      </div>
    </AdminShellV3>
  );
}
```

- [ ] **Step 6: Verify**

```bash
cd frontend/web && npm run dev   # in another terminal: backend on :8000
# open http://localhost:5173/admin?v=3
# expect: new sidebar visible, topbar with "医生 / 选择医生" breadcrumb, no errors in console
# open http://localhost:5173/admin (no ?v=3)
# expect: legacy admin still works exactly as before
```

- [ ] **Step 7: Commit**

```bash
git add frontend/web/src/pages/admin/v3/ frontend/web/src/pages/admin/AdminPage.jsx
git commit -m "feat(admin-v3): mount shell behind ?v=3 query toggle"
```

---

### Task 1.3: Load Material Symbols web font

**Files:**
- Modify: `frontend/web/index.html` — add the Material Symbols `<link>` from the mockup `<head>`

**Why:** Icons in v3 use the Material Symbols Outlined font (variable axes), not `@mui/icons-material` SVGs. One-time load at the root keeps the tree shake clean and avoids per-component imports.

- [ ] **Step 1: Add link tag**

In `frontend/web/index.html`, before `</head>`, add:

```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,300..600,0..1,-25..200" />
```

- [ ] **Step 2: Add a tiny CSS reset for the font**

Append to `frontend/web/src/index.css` (or wherever global styles live):

```css
.material-symbols-outlined {
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20;
  font-size: 20px;
  line-height: 1;
  vertical-align: middle;
  user-select: none;
}
```

- [ ] **Step 3: Verify**

In the dev server, on `/admin?v=3`, sidebar icons render as outlined glyphs (not boxes / not raw text). If the font is still loading you'll see literal text like `dashboard` for ~1s — that's the FOUT, acceptable.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/index.html frontend/web/src/index.css
git commit -m "feat(admin-v3): load Material Symbols Outlined font"
```

---

## Phase 2 — Doctor detail rebuild

All components in this phase live under `frontend/web/src/pages/admin/v3/doctorDetail/`.

Data layer reuses existing endpoints:
- `GET /api/admin/doctors/{id}` — profile + setup + stats_7d
- `GET /api/admin/doctors/{id}/related` — patients/records/messages/suggestions/etc.
- `GET /api/admin/doctors/{id}/timeline?patient_id=…` — per-patient events

A single hook `useDoctorDetail(doctorId)` fetches both `doctors/{id}` and `related` and returns `{ doctor, related, loading, error }`. Each tab consumes `related[tabKey]`.

### Task 2.1: Doctor detail skeleton + 4 tabs + KPI strip

**Files:**
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/AdminDoctorDetailV3.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/DoctorHeader.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/KpiStrip.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/Tabs.jsx`
- Create: `frontend/web/src/pages/admin/v3/hooks/useDoctorDetail.js`
- Modify: `frontend/web/src/pages/admin/v3/index.jsx` — when `?doctor=<id>` is in URL, render `AdminDoctorDetailV3`

- [ ] **Step 1: Implement `useDoctorDetail` hook**

```js
// frontend/web/src/pages/admin/v3/hooks/useDoctorDetail.js
import { useEffect, useState } from "react";
import { getAdminDoctorRelated } from "../../../../api";

const ADMIN_TOKEN_KEY = "adminToken";

async function fetchJson(url) {
  const token = localStorage.getItem(ADMIN_TOKEN_KEY) || (import.meta.env.DEV ? "dev" : "");
  const res = await fetch(url, { headers: token ? { "X-Admin-Token": token } : {} });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export default function useDoctorDetail(doctorId) {
  const [state, setState] = useState({ doctor: null, related: null, loading: true, error: null });
  useEffect(() => {
    if (!doctorId) return;
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    Promise.all([
      fetchJson(`/api/admin/doctors/${doctorId}`),
      getAdminDoctorRelated(doctorId),
    ])
      .then(([doc, rel]) => {
        if (cancelled) return;
        setState({ doctor: { ...doc.profile, setup: doc.setup, stats_7d: doc.stats_7d }, related: rel, loading: false, error: null });
      })
      .catch((e) => !cancelled && setState({ doctor: null, related: null, loading: false, error: e.message }));
    return () => { cancelled = true; };
  }, [doctorId]);
  return state;
}
```

- [ ] **Step 2: Implement `DoctorHeader`**

Mirror the `<section class="dh">` block. Three columns: portrait (44px circle, `infoTint` bg), meta block (name 17px/600 + dept chip + sub-info), actions (3 btns). Reuse `<DhPortrait>` from the mockup pattern. The dept chip is the only place green appears here.

- [ ] **Step 3: Implement `KpiStrip`**

5-cell grid, 14px label, 28px number, mono trend delta. Reads from `doctor.stats_7d`. Spec mapping (from existing API):
- patients → `s.patients`
- messages → `s.messages` (compute trend from prev week if API exposes; otherwise omit `trend`)
- AI 采纳率 → `Math.round(s.ai_adoption * 100)` colored `info`
- P50 → `s.response_p50_hours` (may not exist — show "—" if missing)
- 逾期任务 → `s.overdue_tasks`

- [ ] **Step 4: Implement `Tabs` (4 tabs)**

```jsx
const TABS = [
  { key: "overview",  label: "总览",     icon: "overview" },
  { key: "patients",  label: "患者",     icon: "groups",  count: (rel) => rel?.patients?.count },
  { key: "chat",      label: "沟通",     icon: "forum",   count: (rel) => rel?.messages?.count },
  { key: "ai",        label: "AI 与知识", icon: "network_intelligence", count: (rel) => rel?.suggestions?.count },
];
```

Active tab gets `borderBottom: 2px solid COLOR.brand` and the active icon flips to brand color.

- [ ] **Step 5: Wire `AdminDoctorDetailV3`**

```jsx
export default function AdminDoctorDetailV3({ doctorId }) {
  const { doctor, related, loading, error } = useDoctorDetail(doctorId);
  const [tab, setTab] = useState("overview");
  if (loading) return <SectionLoading />;        // task 4.3
  if (error)   return <SectionError msg={error} />;  // task 4.3
  return (
    <>
      <DoctorHeader doctor={doctor} />
      <KpiStrip stats={doctor.stats_7d} />
      <Tabs value={tab} onChange={setTab} related={related} />
      {tab === "overview" && <OverviewTab doctor={doctor} related={related} />}
      {tab === "patients" && <PatientsTab patients={related.patients?.items || []} />}
      {tab === "chat" && <ChatTab doctorId={doctorId} />}
      {tab === "ai" && <AiTab suggestions={related.suggestions?.items || []} />}
    </>
  );
}
```

- [ ] **Step 6: Wire URL routing in `index.jsx`**

```jsx
// frontend/web/src/pages/admin/v3/index.jsx
const params = new URLSearchParams(window.location.search);
const doctorId = params.get("doctor");
return doctorId
  ? <AdminShellV3 section="doctors" breadcrumb={[{label:"医生"},{label: doctor?.name || doctorId, here:true}]}>
      <AdminDoctorDetailV3 doctorId={doctorId} />
    </AdminShellV3>
  : <AdminShellV3 ...><DoctorList /></AdminShellV3>;
```

- [ ] **Step 7: Verify**

```bash
# pick a real doctor id from the existing /admin (legacy)
# open: http://localhost:5173/admin?v=3&doctor=<id>
# expect: header card, KPI strip with real numbers, 4 tabs, "总览" tab active
# expect: each KPI cell shows actual values from /api/admin/doctors/{id}
```

- [ ] **Step 8: Commit**

```bash
git add frontend/web/src/pages/admin/v3/
git commit -m "feat(admin-v3): doctor detail shell with header + KPI strip + 4 tabs"
```

---

### Task 2.2: 总览 tab — AI adoption, timeline, 关注患者

**Files:**
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/OverviewTab.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/AiAdoptionPanel.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/TimelinePanel.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/AlertList.jsx`

- [ ] **Step 1: Implement `AiAdoptionPanel`**

Layout from the mockup `<div class="panel">…<div class="adoption">…`:
- Left: 40px brand-color number (use `COLOR.brand` even after the trim — this IS where green earns its place, it's the AI adoption rate)
- Right: 3-row breakdown (采纳/编辑后采纳/拒绝)
- Below: stacked bar (60% accept brand / 18% edit info / 22% reject danger)
- Below: 600x130 SVG area chart

Data: pull from `/api/admin/overview` `secondary` block (already returns adoption stats).

- [ ] **Step 2: Implement `TimelinePanel`**

Mirror `<div class="timeline">` with day headers + rows. Each row: time (mono), tinted icon box (44px round, `ic-msg`/`ic-ai`/`ic-record`/`ic-task` color variants), detail text, status chip. Group items by day from `/api/admin/activity?doctor_id=<id>&days=7`.

The icon-box color map is literal:
```js
const ICON_BG = { msg: COLOR.infoTint, ai: COLOR.warningTint, record: COLOR.brandTint, task: COLOR.dangerTint };
const ICON_FG = { msg: COLOR.info,     ai: COLOR.warning,     record: COLOR.brand,     task: COLOR.danger };
```

- [ ] **Step 3: Implement `AlertList`**

`需要关注` panel — `panel.rail-danger` (left rail = danger). Three card rows: high-risk (danger-tint bg + "高危" pill), warn (warning-tint bg), neutral (cardAlt bg + subtle border). Pulls from `/api/admin/doctors/{id}/related` → derived `flagged_patients` array.

If the API doesn't yet expose `flagged_patients`, show empty state from task 4.3 with text "暂无标记患者".

- [ ] **Step 4: Compose `OverviewTab`**

```jsx
export default function OverviewTab({ doctor, related }) {
  return (
    <div style={{ paddingTop: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16, marginBottom: 14 }}>
        <AiAdoptionPanel doctorId={doctor.doctor_id} />
        <AlertList patients={related?.flaggedPatients || []} />
      </div>
      <TimelinePanel doctorId={doctor.doctor_id} />
    </div>
  );
}
```

- [ ] **Step 5: Verify**

Open `/admin?v=3&doctor=<id>`. Visual check against the mockup — same layout, real data. Adoption number, area chart shape, timeline rows with proper status chips.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(admin-v3): 总览 tab — AI adoption + timeline + 关注 list"
```

---

### Task 2.3: 患者 tab — filter bar + patient grid

**Files:**
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/PatientsTab.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/PatientFilterBar.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/PatientCard.jsx`
- Create: `frontend/web/src/pages/admin/v3/hooks/usePatientFilter.js`
- Create: `frontend/web/test/hooks/usePatientFilter.test.js`

- [ ] **Step 1: Write failing test for the filter reducer**

```js
// frontend/web/test/hooks/usePatientFilter.test.js
import { describe, it, expect } from "vitest";
import { applyFilter } from "../../src/pages/admin/v3/hooks/usePatientFilter";

const SAMPLE = [
  { id: 1, name: "陈玉琴", risk: "warn",    silentDays: 0,  isPostOp: false },
  { id: 2, name: "周建国", risk: null,      silentDays: 1,  isPostOp: true  },
  { id: 3, name: "林文华", risk: "danger",  silentDays: 0,  isPostOp: false },
  { id: 4, name: "何建华", risk: null,      silentDays: 12, isPostOp: false },
];

describe("applyFilter", () => {
  it("returns all when filter='all'", () => {
    expect(applyFilter(SAMPLE, "all")).toHaveLength(4);
  });
  it("returns only danger when filter='danger'", () => {
    expect(applyFilter(SAMPLE, "danger").map(p => p.name)).toEqual(["林文华"]);
  });
  it("returns only warn (未达标) when filter='warn'", () => {
    expect(applyFilter(SAMPLE, "warn").map(p => p.name)).toEqual(["陈玉琴"]);
  });
  it("returns silent>=7 when filter='silent'", () => {
    expect(applyFilter(SAMPLE, "silent").map(p => p.name)).toEqual(["何建华"]);
  });
  it("returns post-op when filter='postop'", () => {
    expect(applyFilter(SAMPLE, "postop").map(p => p.name)).toEqual(["周建国"]);
  });
});
```

- [ ] **Step 2: Run failing test**

```bash
cd frontend/web && npx vitest run test/hooks/usePatientFilter.test.js
# expect: FAIL — applyFilter not defined
```

- [ ] **Step 3: Implement `usePatientFilter` + `applyFilter`**

```js
// frontend/web/src/pages/admin/v3/hooks/usePatientFilter.js
import { useMemo, useState } from "react";

export function applyFilter(patients, filter) {
  switch (filter) {
    case "danger": return patients.filter(p => p.risk === "danger");
    case "warn":   return patients.filter(p => p.risk === "warn");
    case "silent": return patients.filter(p => (p.silentDays ?? 0) >= 7);
    case "postop": return patients.filter(p => p.isPostOp);
    case "all":
    default:       return patients;
  }
}

export default function usePatientFilter(patients) {
  const [filter, setFilter] = useState("all");
  const counts = useMemo(() => ({
    all:    patients.length,
    danger: patients.filter(p => p.risk === "danger").length,
    warn:   patients.filter(p => p.risk === "warn").length,
    silent: patients.filter(p => (p.silentDays ?? 0) >= 7).length,
    postop: patients.filter(p => p.isPostOp).length,
  }), [patients]);
  const filtered = useMemo(() => applyFilter(patients, filter), [patients, filter]);
  return { filter, setFilter, filtered, counts };
}
```

- [ ] **Step 4: Run test, expect PASS**

- [ ] **Step 5: Implement `PatientCard`**

Mirror `<div class="pc">` from the mockup. Add `pc.danger` variant (with the 2px left rail) when `patient.risk === "danger"`. Sparkline = inline SVG polyline, stroke color = brand for stable / danger for risk / text-3 for inactive.

- [ ] **Step 6: Implement `PatientFilterBar`**

5 chips + sort. Active chip on neutral (`bgCanvas` bg, dark text) per the v3 polish. Counts come from `usePatientFilter`.

- [ ] **Step 7: Compose `PatientsTab`**

```jsx
export default function PatientsTab({ patients }) {
  const { filter, setFilter, filtered, counts } = usePatientFilter(patients);
  return (
    <Panel title="王医生的患者" aside={`${patients.length} 位`}>
      <PatientFilterBar filter={filter} onChange={setFilter} counts={counts} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, padding: "12px 14px" }}>
        {filtered.map(p => <PatientCard key={p.id} patient={p} />)}
      </div>
    </Panel>
  );
}
```

- [ ] **Step 8: Verify**

```bash
npx vitest run test/hooks/usePatientFilter.test.js   # all green
# manual: /admin?v=3&doctor=<id> → click 患者 tab → click 高危 chip → grid filters
```

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(admin-v3): 患者 tab with filter bar + card grid (TDD on filter reducer)"
```

---

### Task 2.4: 沟通 tab — chat thread + AI footnote

**Files:**
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/ChatTab.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/ChatList.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/ChatThread.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/AiFootnoteCard.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/AdoptionTrace.jsx`

**Why:** This is the most distinctive screen in the redesign. The AI-as-footnote pattern is the contract — it must read clearly as NOT a real outbound message.

- [ ] **Step 1: Implement `ChatList` (left rail)**

Grouped patient list with avatar / name+risk-pill / snippet / timestamp. Active row has 2px brand left rail + brand avatar fill. Search input on top. Reads from `related.messages` deduped by `patient_id` with last message as snippet.

- [ ] **Step 2: Implement `ChatThread` (right pane)**

Three message types interleaved by timestamp:
1. `<Bubble role="patient">` — left-aligned, white-card, asymmetric corner (`12 12 12 4`)
2. `<Bubble role="doctor">` — right-aligned, `COLOR.brand` fill, white text, asymmetric `12 12 4 12`
3. `<AiFootnoteCard>` — narrow (max 360px), bracket connector, **always right-aligned even though it's not a doctor message** (anchored to the doctor's reply that consumed it OR to the patient message it's analyzing — the API gives us `related_message_id`)

Day tags between messages when day changes.

- [ ] **Step 3: Implement `AiFootnoteCard` (the high-stakes component)**

```jsx
export default function AiFootnoteCard({ kind, summary, body, sources }) {
  // kind: "analysis" | "draft" — same chrome, different label.
  const [expanded, setExpanded] = useState(kind === "draft"); // drafts open by default
  return (
    <div style={{ alignSelf: "flex-end", display: "flex", maxWidth: 360, marginTop: -2 }}>
      <Bracket />
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          flex: 1,
          background: COLOR.infoTint,                 // STAYS infoTint when expanded (codex v3 fix)
          border: `1px dashed ${COLOR.info}`,         // STAYS dashed when expanded (codex v3 fix)
          borderRadius: 6,
          padding: "7px 10px",
          fontSize: 12,
          color: COLOR.text2,
          cursor: "pointer",
        }}
      >
        <FootnoteHeader kind={kind} expanded={expanded} />
        <div style={{ fontSize: 11.5, marginTop: 3 }}>{summary}</div>
        {expanded && (
          <>
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px dashed ${COLOR.borderSubtle}`,
                          fontSize: 12.5, lineHeight: 1.55, color: COLOR.text1 }}>
              {body}
            </div>
            <SourceChips sources={sources} />
          </>
        )}
      </div>
    </div>
  );
}
```

The `Bracket` is the visual anchor — left border 2px + top + bottom + radius `0 0 0 6px` so it hugs the message above.

**Critical:** `.ai-card.expanded` must keep `infoTint` bg + `dashed` border per codex v3 review. Do not switch to white + solid.

- [ ] **Step 4: Implement `AdoptionTrace`**

The tiny pill row that appears AFTER a doctor reply consumed an AI draft. Pill text: "医生修改后发送" / "直接采纳" / "改写". Plus a sentence with the diff summary. Compact — single line, 11.5px, right-aligned.

- [ ] **Step 5: Compose `ChatTab`**

```jsx
export default function ChatTab({ doctorId }) {
  const [activePatientId, setActivePatientId] = useState(null);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", height: 700,
                  background: COLOR.bgCard, border: `1px solid ${COLOR.borderSubtle}`,
                  borderRadius: 12, overflow: "hidden", boxShadow: SHADOW.s1, marginTop: 16 }}>
      <ChatList doctorId={doctorId} activeId={activePatientId} onSelect={setActivePatientId} />
      {activePatientId
        ? <ChatThread doctorId={doctorId} patientId={activePatientId} />
        : <ChatEmptyState />}
    </div>
  );
}
```

- [ ] **Step 6: Verify**

Open `/admin?v=3&doctor=<id>` → 沟通 tab → click a patient. Expect: chat thread with bubbles + at least one collapsed AI footnote. Click footnote → expands inline, infoTint bg stays. The AI footnote should never be confused for a doctor's message at scroll speed.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(admin-v3): 沟通 tab — chat thread with AI-as-footnote pattern"
```

---

### Task 2.5: AI 与知识 tab — decision cards + triptych

**Files:**
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/AiTab.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/DecisionCard.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/Triptych.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/KbCitation.jsx`
- Create: `frontend/web/src/pages/admin/v3/doctorDetail/RiskTagRow.jsx`
- Create: `frontend/web/test/admin-v3/decisionCardData.test.js`

- [ ] **Step 1: Write failing test for the data shape**

`/api/admin/doctors/{id}/related` returns `suggestions.items[]` with mixed schema. We need a transform `toDecisionCards(items)` that returns the 4-block shape: `{ patient, kind, observation, evidence[], risks[], outcome }`.

```js
// frontend/web/test/admin-v3/decisionCardData.test.js
import { describe, it, expect } from "vitest";
import { toDecisionCards } from "../../src/pages/admin/v3/doctorDetail/decisionCardData";

const RAW = [{
  id: 1, patient_name: "陈玉琴",
  section: "treatment",
  content: "建议氨氯地平 5→10mg",
  decision: "edited",
  cited_knowledge_ids: [12],
  cited_knowledge: [{ id: 12, title: "高血压调药梯度", quote: "先加量再加药" }],
  doctor_reply: "陈阿姨好，氨氯地平加到 10mg…",
  risk_tags: ["med_change"],
  created_at: "2026-04-24T14:42:00Z",
}];

describe("toDecisionCards", () => {
  it("maps section=treatment to kind=reply_suggestion", () => {
    const cards = toDecisionCards(RAW);
    expect(cards[0].kind).toBe("reply_suggestion");
  });
  it("preserves citations as evidence array", () => {
    expect(toDecisionCards(RAW)[0].evidence).toEqual([{ num: 12, title: "高血压调药梯度", quote: "先加量再加药" }]);
  });
  it("derives outcome.badge from decision field", () => {
    expect(toDecisionCards(RAW)[0].outcome.badge).toBe("edited");
  });
});
```

- [ ] **Step 2: Run test → FAIL**

- [ ] **Step 3: Implement `decisionCardData.toDecisionCards`**

Pure transform. No fetching here — that's done by the parent.

- [ ] **Step 4: Implement `DecisionCard`**

4 blocks in stable order: AI 观察 → 依据 → 触发规则 → 医生处理. Each block has icon + uppercase 11px label + content. Card gets `dc.danger` variant (left rail = danger) when `kind === "danger_signal"`, `dc.info` when `kind === "reply_suggestion"`.

The 医生处理 block contents differ by `kind`:
- `danger_signal`: short prose (`<DcText>`)
- `reply_suggestion`: `<Triptych aiDraft={...} sentVersion={...} reason={...} />`

- [ ] **Step 5: Implement `Triptych`**

3-column grid: `1fr 1fr 200px`. Last column (`修改原因`) on `bgCardAlt`. Mobile: stack to single column (handled in task 4.3).

- [ ] **Step 6: Implement `KbCitation` (`<div class="kb-item">`)**

Cream/info-tint bg, info-color left bar, mono num + bold title + quote.

- [ ] **Step 7: Compose `AiTab`**

```jsx
export default function AiTab({ suggestions }) {
  const cards = toDecisionCards(suggestions);
  if (cards.length === 0) return <EmptyState message="暂无 AI 决策记录" />;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14, paddingTop: 16 }}>
      {cards.map(c => <DecisionCard key={c.id} card={c} />)}
    </div>
  );
}
```

- [ ] **Step 8: Verify + commit**

```bash
npx vitest run test/admin-v3/decisionCardData.test.js   # green
# manual: AI 与知识 tab shows the decision cards
git commit -m "feat(admin-v3): AI 与知识 tab — decision cards with triptych"
```

---

## Phase 3 — 运营 module

### Task 3.1: 运营 routing + page shell

**Files:**
- Create: `frontend/web/src/pages/admin/v3/ops/OpsPage.jsx`
- Modify: `frontend/web/src/pages/admin/v3/index.jsx` — route `?section=ops/<sub>` to OpsPage
- Modify: `frontend/web/src/pages/admin/v3/AdminSidebar.jsx` — make ops nav-items navigable

OpsPage takes a `subsection` prop (`"invites" | "pilot" | "report" | "export"`) and renders the corresponding sub-page. Rest of this phase fills those in.

- [ ] **Step 1: Implement OpsPage shell**
- [ ] **Step 2: Wire sidebar links to update URL via `?section=ops/invites` etc.**
- [ ] **Step 3: Verify routing — clicking 邀请码 changes URL and breadcrumb**
- [ ] **Step 4: Commit** — `feat(admin-v3): 运营 module routing shell`

---

### Task 3.2: 邀请码 page

**Files:**
- Create: `frontend/web/src/pages/admin/v3/ops/InviteCodes.jsx`

Reuses existing `GET /api/admin/invites` (`invite_handlers.py:45`). Renders the `ops-card` "邀请码使用" + a table of all codes with status/usage.

- [ ] **Steps 1-4: read API contract, render meter card + table, wire copy-to-clipboard, verify, commit**

Commit: `feat(admin-v3): 邀请码 page (read-only view of invite codes)`

---

### Task 3.3: 试点进度 + 合作伙伴报表 + new endpoints

**Files:**
- Create: `frontend/web/src/pages/admin/v3/ops/PilotProgress.jsx`
- Create: `frontend/web/src/pages/admin/v3/ops/PartnerReport.jsx`
- Create: `src/channels/web/doctor_dashboard/admin_ops.py` — new router with two GET endpoints
- Modify: `src/channels/web/doctor_dashboard/__init__.py` (or wherever routers are mounted) — register `admin_ops.router`

**Endpoints:**
- `GET /api/admin/ops/pilot-progress` → `{ start_date, current_week, total_weeks, milestones: [{date, label, done}], doctors_active, doctors_target }`
- `GET /api/admin/ops/partner-report?week=YYYY-Wxx` → `{ adoption, patient_active, danger_signals_triggered, top_doctors }`

For now, both endpoints return computed values from existing tables (no new DB columns).

- [ ] **Step 1: Implement `admin_ops.py`** (mirror the structure of `admin_overview.py:49`'s router)
- [ ] **Step 2: Add Vitest for the JSX + a Python pytest for the endpoints (`tests/test_admin_ops.py`)**
- [ ] **Step 3: Verify backend** — `curl localhost:8000/api/admin/ops/pilot-progress -H "X-Admin-Token: dev"` returns valid JSON
- [ ] **Step 4: Wire the JSX pages to the new endpoints**
- [ ] **Step 5: Commit** — `feat(admin-v3): 运营 / 试点进度 + 合作伙伴报表 (new endpoints)`

---

## Phase 4 — Permissions + polish

### Task 4.1: Viewer-role admin token

**Files:**
- Modify: `src/channels/web/doctor_dashboard/deps.py` — accept second token, return `{ role: "viewer" | "super" }` from the dep
- Modify: `src/channels/web/doctor_dashboard/admin_cleanup.py` — gate destructive routes on `role == "super"`
- Create: `tests/test_admin_viewer_role.py`

- [ ] **Step 1: Write failing pytest**

```python
# tests/test_admin_viewer_role.py
def test_viewer_token_can_read_overview(client, monkeypatch):
    monkeypatch.setenv("UI_ADMIN_TOKEN",        "super-token")
    monkeypatch.setenv("UI_ADMIN_VIEWER_TOKEN", "viewer-token")
    r = client.get("/api/admin/overview", headers={"X-Admin-Token": "viewer-token"})
    assert r.status_code == 200

def test_viewer_token_cannot_cleanup(client, monkeypatch):
    monkeypatch.setenv("UI_ADMIN_TOKEN",        "super-token")
    monkeypatch.setenv("UI_ADMIN_VIEWER_TOKEN", "viewer-token")
    r = client.post("/api/admin/cleanup/execute?action=test_doctors",
                    headers={"X-Admin-Token": "viewer-token"})
    assert r.status_code == 403
```

- [ ] **Step 2: Run → FAIL** (current code doesn't know about viewer)
- [ ] **Step 3: Modify `deps.py` to accept `UI_ADMIN_VIEWER_TOKEN` and add a `require_admin_super` dependency**
- [ ] **Step 4: Replace `require_admin_token` with `require_admin_super` in cleanup endpoints**
- [ ] **Step 5: Run pytest → PASS**
- [ ] **Step 6: Commit** — `feat(admin-v3): viewer-role admin token (read-only access)`

---

### Task 4.2: Dev-mode toggle + hide cleanup UI

**Files:**
- Modify: `frontend/web/src/pages/admin/v3/AdminSidebar.jsx` — wire user-menu popover with dev-mode switch
- Create: `frontend/web/src/pages/admin/v3/devMode.js` — `isDevMode()` checks `localStorage.getItem("adminDevMode") === "1"` AND admin role is `super`
- Modify: `frontend/web/src/pages/admin/v3/AdminSidebar.jsx` — only render 系统 group when `isDevMode()`

The user-menu shows the role ("合作伙伴 · 只读" or "管理员") under the name. The dev-mode switch is hidden for `viewer` role entirely.

- [ ] **Step 1: implement `devMode.js`**
- [ ] **Step 2: render conditional sidebar groups**
- [ ] **Step 3: verify visually — viewer token sees no 系统 group, no dev toggle**
- [ ] **Step 4: commit** — `feat(admin-v3): dev-mode toggle behind user menu`

---

### Task 4.3: Empty / loading / error states + mobile

**Files:**
- Create: `frontend/web/src/pages/admin/v3/components/EmptyState.jsx`
- Create: `frontend/web/src/pages/admin/v3/components/SectionLoading.jsx`
- Create: `frontend/web/src/pages/admin/v3/components/SectionError.jsx`
- Create: `frontend/web/src/pages/admin/v3/components/SkeletonLine.jsx`
- Modify: `frontend/web/src/pages/admin/v3/AdminShellV3.jsx` — add `@media (max-width: 768px)` rules

Implementations match the mockup `<div class="state-card">` blocks (44px circle icon + title + desc + CTA), and the `@media` block at the bottom of the v3 mockup CSS.

- [ ] **Step 1: implement state components**
- [ ] **Step 2: replace inline loading/error spinners across all v3 components with these**
- [ ] **Step 3: add mobile breakpoint**
- [ ] **Step 4: verify on devtools mobile viewport (375x667) — sidebar hides, KPI 2x2, chat single-column**
- [ ] **Step 5: commit** — `feat(admin-v3): empty/loading/error states + mobile breakpoint`

---

## Phase 5 — Cutover

### Task 5.1: Playwright e2e for v3

**Files:**
- Create: `frontend/web/tests/admin-v3.spec.ts`

Test plan (per CLAUDE.md selector rules — `getByText`, not `getByRole("button")`):

- visits `/admin?v=3` and sees the new sidebar
- clicks 全体医生 → sees doctor list
- clicks a doctor → sees doctor detail with 4 tabs
- clicks 患者 tab → sees filter chips → click 高危 → grid filters
- clicks 沟通 tab → click a patient → sees chat thread → click AI footnote → expands inline (still infoTint bg)
- clicks AI 与知识 tab → sees decision cards
- viewer token (set localStorage `adminToken=<viewer>`) → no 系统 group, no dev toggle visible

- [ ] **Step 1: write the spec**
- [ ] **Step 2: run** — `cd frontend/web && rm -rf test-results && npx playwright test admin-v3.spec.ts`
- [ ] **Step 3: produce video readme per CLAUDE.md E2E section**
- [ ] **Step 4: commit** — `test(admin-v3): playwright e2e covering all 4 tabs + viewer role`

---

### Task 5.2: Switch default + deprecate v1

**Files:**
- Modify: `frontend/web/src/pages/admin/AdminPage.jsx` — invert the toggle: default to v3, mount v1 only when `?v=1`
- Modify: `docs/specs/2026-04-24-admin-modern-mockup-v3.html` — leave as-is (now historical reference)
- Mark deprecated: `frontend/web/src/pages/admin/AdminOverview.jsx`, `AdminDoctorDetail.jsx`, `AdminRawData.jsx` — add a top-of-file comment "deprecated 2026-MM-DD; see v3/. Remove after one release if no regressions."

Do NOT delete v1 yet. Keep one release as a fallback in case 陈宇明 hits a regression.

- [ ] **Step 1: invert toggle**
- [ ] **Step 2: mark v1 deprecated (comments only)**
- [ ] **Step 3: verify** — `/admin` (no query) lands on v3, `/admin?v=1` still shows v1
- [ ] **Step 4: commit** — `feat(admin-v3): default to v3, fallback to v1 via ?v=1`

---

## Self-review

**Spec coverage:**
- v3 mockup sidebar (5 sections + dev toggle + user menu) → Tasks 1.2, 4.2 ✓
- Doctor header + KPI strip + 4 tabs → Task 2.1 ✓
- 总览 (AI adoption, timeline, 关注) → Task 2.2 ✓
- 患者 (filter bar + grid + sparkline cards) → Task 2.3 ✓
- 沟通 (chat list + thread + AI footnote + adoption trace) → Task 2.4 ✓
- AI 与知识 (decision cards + triptych + KB citations) → Task 2.5 ✓
- 运营 (邀请码 / 试点 / 报表) → Tasks 3.1-3.3 ✓
- States (empty/loading/error) + mobile → Task 4.3 ✓
- Viewer role + dev-mode toggle → Tasks 4.1, 4.2 ✓
- E2E coverage → Task 5.1 ✓
- Cutover → Task 5.2 ✓

**Open spec gap:** the mockup shows audit log as a sidebar item (under 系统) but I did not write an `AdminAuditLog` page. The existing legacy admin already exposes audit data via `AdminRawData.jsx` (`audit_log` table). For v3 we'll just sidebar-link to `?v=1&section=audit_log` until someone asks for a dedicated v3 audit page. If the partner doctor needs auditability earlier, add Task 4.4: AuditLog page (similar to OpsPage shell + a paginated table of audit events).

**Type consistency check:**
- `applyFilter` (Task 2.3) → same name, same args throughout
- `toDecisionCards` (Task 2.5) → same name throughout
- `useDoctorDetail` returns `{ doctor, related, loading, error }` — referenced consistently in Tasks 2.1-2.5
- `COLOR.brand` vs hardcoded `#07C160` — always use `COLOR.brand`
- `AiFootnoteCard` props `{ kind, summary, body, sources }` — defined Task 2.4, consumed only there

**Risks:**
1. **Existing endpoints may not return the exact shape components expect.** Mitigation: each tab task starts by reading the actual API response (curl + jq), and adds a server-side transform if the shape is wrong, rather than papering over in JSX.
2. **`?v=3` toggle leaks into URLs that get shared.** Acceptable — the toggle is the rollout strategy. Once Task 5.2 ships, default is v3, query toggle becomes `?v=1` for fallback.
3. **AI footnote anchoring** depends on the API exposing which AI suggestion fed which doctor reply. If `messages` table doesn't link to `ai_suggestions`, the footnote-after-doctor-reply flow looks orphaned. Mitigation: in Task 2.4, check `MessageDB.ai_suggestion_id` field; if absent, file a follow-up to add it (small backend migration).
4. **Material Symbols font is loaded from Google Fonts.** Hospital networks may block `fonts.googleapis.com`. Mitigation: in Task 1.3, if Google Fonts is blocked in prod, self-host the font (one-time download). For now keep CDN — partner doctor demo runs on dev server.

**Frequent commits:** every task commits at the end. Phases 1-2 produce ~8 commits. Phases 3-5 produce ~7. Total ~15 commits.

---

**Plan complete and saved to `docs/plans/2026-04-24-admin-modern-port.md`.**
