# Single-Tab IA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the doctor app's 3-tab IA (我的AI / 患者 / 审核) into a single home (`/doctor/my-ai`); delete `/doctor/review` queue list; make `/patients` and `/review/:id` true push subpages with a home-icon shortcut on every subpage NavBar.

**Architecture:** `DoctorPage` shell stops rendering `PatientsPage` / `ReviewQueuePage` as base sections — `MyAIPage` is the only base. Other doctor routes reach the user via the existing `usePageStack` overlay mechanism. Each subpage renders its own `NavBar` with a `[← 🏠]` cluster; ReviewPage auto-advances to the next pending item on finalize. Cold-start deep-links seed a synthetic `/doctor/my-ai` history entry so back-tap unwinds correctly.

**Tech Stack:** React, react-router-dom v6, antd-mobile, framer-motion, Vitest + @testing-library/react.

**Source spec:** [docs/superpowers/specs/2026-04-26-single-tab-ia-design.md](../specs/2026-04-26-single-tab-ia-design.md)

---

## File Structure

**Create:**
- `frontend/web/src/v2/components/SubpageBackHome.jsx` — shared back+home cluster for `NavBar.backArrow` slot
- `frontend/web/src/v2/components/__tests__/SubpageBackHome.test.jsx` — unit test for the cluster
- `frontend/web/src/v2/coldStartSeed.js` — pure helper deciding when to seed a synthetic /doctor/my-ai history entry
- `frontend/web/src/v2/__tests__/coldStartSeed.test.js` — unit tests for the seed decision
- `frontend/web/src/v2/pages/doctor/reviewAutoAdvance.js` — pure helper computing next-review-id navigation
- `frontend/web/src/v2/pages/doctor/__tests__/reviewAutoAdvance.test.js` — unit tests for the helper
- `frontend/web/src/v2/__tests__/single-tab-ia.test.jsx` — integration tests adopted from codex's list

**Modify (major):**
- `frontend/web/src/v2/pages/doctor/DoctorPage.jsx` — delete TabBar, TABS, badges, `ReviewQueuePage`/`PatientsPage` base-section branches, conditional NavBar; simplify `baseSection` to always `my-ai`
- `frontend/web/src/v2/pages/doctor/MyAIPage.jsx` — swap quickAction tile, retarget triage row, drop "全部事项 ›" link, add bottom safe-area
- `frontend/web/src/v2/pages/doctor/PatientsPage.jsx` — add own NavBar with back+home + title + "+" right action
- `frontend/web/src/v2/pages/doctor/ReviewPage.jsx` — auto-advance on finalize + back+home cluster
- `frontend/web/src/v2/App.jsx` — cold-start deep-link history seed

**Modify (sweep — back+home cluster only):**
- `frontend/web/src/v2/pages/doctor/PatientDetail.jsx`
- `frontend/web/src/v2/pages/doctor/PatientChatPage.jsx`
- `frontend/web/src/v2/pages/doctor/SettingsPage.jsx`
- `frontend/web/src/v2/pages/doctor/OnboardingWizard.jsx`
- `frontend/web/src/v2/pages/doctor/settings/PersonaSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/KnowledgeSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/AddKnowledgeSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/KnowledgeDetailSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/TeachByExampleSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/PendingReviewSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/PersonaOnboardingSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/TemplateSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/QrSubpage.jsx`

**Delete:**
- `frontend/web/src/v2/pages/doctor/ReviewQueuePage.jsx`

---

## Pre-flight

Verify the working tree is clean and the dev servers are not running on `:8000` / `:5173` (per repo policy: no hot reload during this kind of refactor).

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent
git status --porcelain
lsof -i :8000 -sTCP:LISTEN 2>/dev/null
lsof -i :5173 -sTCP:LISTEN 2>/dev/null
```

If any are running, stop them so each task's lint/test runs are deterministic.

---

## Task 1: Create `SubpageBackHome` shared component

**Why:** 13+ subpages need the same back+home cluster. A shared component keeps the markIntentionalBack logic in one place and avoids JSX duplication.

**Files:**
- Create: `frontend/web/src/v2/components/SubpageBackHome.jsx`
- Test: `frontend/web/src/v2/components/__tests__/SubpageBackHome.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/web/src/v2/components/__tests__/SubpageBackHome.test.jsx`:

```jsx
import { describe, test, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import SubpageBackHome from "../SubpageBackHome";
import * as navDirection from "../../../hooks/useNavDirection";

function HostedRoutes({ initialPath = "/start" }) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/start" element={<SubpageBackHome />} />
        <Route path="/doctor/my-ai" element={<div>HOME</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("SubpageBackHome", () => {
  beforeEach(() => {
    vi.spyOn(navDirection, "markIntentionalBack").mockImplementation(() => {});
  });

  test("renders back arrow and home icon", () => {
    render(<HostedRoutes />);
    expect(screen.getByLabelText("返回")).toBeInTheDocument();
    expect(screen.getByLabelText("回到首页")).toBeInTheDocument();
  });

  test("home icon click navigates to /doctor/my-ai and marks intentional back", () => {
    render(<HostedRoutes />);
    fireEvent.click(screen.getByLabelText("回到首页"));
    expect(navDirection.markIntentionalBack).toHaveBeenCalled();
    expect(screen.getByText("HOME")).toBeInTheDocument();
  });

  test("home icon click does NOT bubble to parent (stopPropagation)", () => {
    const parentClick = vi.fn();
    const { container } = render(
      <MemoryRouter initialEntries={["/start"]}>
        <div onClick={parentClick} data-testid="parent">
          <Routes>
            <Route path="/start" element={<SubpageBackHome />} />
          </Routes>
        </div>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByLabelText("回到首页"));
    expect(parentClick).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend/web
npx vitest run src/v2/components/__tests__/SubpageBackHome.test.jsx
```

Expected: FAIL with "Cannot find module '../SubpageBackHome'".

- [ ] **Step 3: Write minimal implementation**

Create `frontend/web/src/v2/components/SubpageBackHome.jsx`:

```jsx
/**
 * Shared back-arrow + home-icon cluster for any push subpage's NavBar.
 *
 * Usage:
 *   <NavBar
 *     backArrow={<SubpageBackHome />}
 *     onBack={() => navigate(-1)}
 *   >
 *     {title}
 *   </NavBar>
 *
 * The home icon stops propagation so tapping it does not also fire `onBack`.
 * Both interactions go through markIntentionalBack() so the slide-out
 * animation plays via useNavDirection.
 */
import { useNavigate } from "react-router-dom";
import { LeftOutline } from "antd-mobile-icons";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import { markIntentionalBack } from "../../hooks/useNavDirection";
import { APP, ICON } from "../theme";
import { dp } from "../../utils/doctorBasePath";

export default function SubpageBackHome() {
  const navigate = useNavigate();

  function handleHomeClick(e) {
    e.stopPropagation();
    markIntentionalBack();
    navigate(dp("my-ai"));
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <span aria-label="返回" style={{ display: "inline-flex" }}>
        <LeftOutline />
      </span>
      <HomeOutlinedIcon
        aria-label="回到首页"
        role="button"
        tabIndex={0}
        onClick={handleHomeClick}
        sx={{ fontSize: ICON.sm, color: APP.text2, cursor: "pointer" }}
      />
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend/web
npx vitest run src/v2/components/__tests__/SubpageBackHome.test.jsx
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/components/SubpageBackHome.jsx frontend/web/src/v2/components/__tests__/SubpageBackHome.test.jsx
git commit -m "feat(v2): add SubpageBackHome shared back+home cluster for subpage NavBars"
```

---

## Task 2: DoctorPage — delete TabBar, TABS, badges, handleTabChange

**Why:** TabBar is the visible chrome; TABS / badges / handleTabChange are its supporting state. All go.

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/DoctorPage.jsx`
- Test: `frontend/web/src/v2/__tests__/single-tab-ia.test.jsx` (new file)

- [ ] **Step 1: Write the failing test**

Create `frontend/web/src/v2/__tests__/single-tab-ia.test.jsx`:

```jsx
import { describe, test, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock all the doctor query hooks to avoid real fetches
vi.mock("../../lib/doctorQueries", () => ({
  usePatients: () => ({ data: [], isLoading: false }),
  useReviewQueue: () => ({ data: [], isLoading: false }),
  usePersona: () => ({ data: {} }),
  useTodaySummary: () => ({ data: null, isLoading: false }),
  useKbPending: () => ({ data: [] }),
  useKnowledgeItems: () => ({ data: [] }),
  useAIAttention: () => ({ data: { patients: [] } }),
  useUnseenPatientCount: () => ({ data: 0 }),
}));
vi.mock("../../store/doctorStore", () => ({
  useDoctorStore: () => ({ doctorId: "doc1" }),
}));

import DoctorPage from "../pages/doctor/DoctorPage";

function Host({ initialPath = "/doctor/my-ai" }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <DoctorPage doctorId="doc1" />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Single-tab IA — TabBar absence", () => {
  test("DoctorPage renders no .adm-tab-bar element", () => {
    const { container } = render(<Host />);
    expect(container.querySelector(".adm-tab-bar")).toBeNull();
  });

  test("DoctorPage renders no element with role=tablist", () => {
    render(<Host />);
    expect(screen.queryByRole("tablist")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend/web
npx vitest run src/v2/__tests__/single-tab-ia.test.jsx
```

Expected: FAIL — `.adm-tab-bar` is currently rendered.

- [ ] **Step 3: Implement — delete TabBar block, TABS, badges, handleTabChange**

In `frontend/web/src/v2/pages/doctor/DoctorPage.jsx`:

1. Delete the `TABS` array (currently around lines 48–75).
2. Delete the `useState({ review: 0, patients: 0 })` for `badges`.
3. Delete the `handleTabChange` function.
4. Delete the entire `<TabBar>` JSX block at the end of the shell render. This block also contains the `<SafeArea position="bottom" />` line — remove that too (it will move to MyAIPage in Task 9).
5. Remove the `TabBar` import from the antd-mobile import.
6. Remove the now-unused tab-icon imports: `PeopleAltIcon`, `MailIcon`, `MailOutlinedIcon`, `AutoAwesomeIcon`, `AutoAwesomeOutlinedIcon`. Verify each by grepping the file:

```bash
grep -n "PeopleAltIcon\|MailIcon\|MailOutlinedIcon\|AutoAwesomeIcon\|AutoAwesomeOutlinedIcon" frontend/web/src/v2/pages/doctor/DoctorPage.jsx
```

If grep shows the import line is the only reference, remove the import. (`PeopleAltOutlinedIcon` is also tab-only in DoctorPage; remove its import too — `MyAIPage` imports it independently in Task 9.)

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend/web
npx vitest run src/v2/__tests__/single-tab-ia.test.jsx
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/DoctorPage.jsx frontend/web/src/v2/__tests__/single-tab-ia.test.jsx
git commit -m "refactor(v2): remove TabBar, TABS, badges from DoctorPage shell"
```

---

## Task 3: DoctorPage — collapse base section to always my-ai, drop PatientsPage/ReviewQueuePage rendering

**Why:** With TabBar gone, the only valid base section is `my-ai`. PatientsPage and ReviewQueuePage stop rendering as base sections — the former becomes a push subpage (Task 5), the latter is deleted (Task 4).

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/DoctorPage.jsx`
- Test: `frontend/web/src/v2/__tests__/single-tab-ia.test.jsx`

- [ ] **Step 1: Add failing test**

Append to `frontend/web/src/v2/__tests__/single-tab-ia.test.jsx`:

```jsx
describe("Single-tab IA — base section is always my-ai", () => {
  test("at /doctor/patients, MyAIPage is rendered as base; PatientsPage shows as overlay", () => {
    render(<Host initialPath="/doctor/patients" />);
    // MyAIPage's identity card text or hero title is a stable marker
    expect(screen.queryByText(/我的AI|您的专属医疗AI助手/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend/web
npx vitest run src/v2/__tests__/single-tab-ia.test.jsx
```

Expected: FAIL — currently PatientsPage replaces MyAIPage at `/doctor/patients`.

- [ ] **Step 3: Implement — collapse baseSection switch**

In `DoctorPage.jsx`:

1. Find `detectSection()`. Change all return values that were `"patients"` or `"review"` to `"my-ai"` (so `baseSection` is always `my-ai`). Keep the function itself for the overlay-key path (which still needs to detect `patient-{id}`, `review-{id}`, `settings-*`, etc.).
2. Find the JSX that renders `baseSection === "patients" ? <PatientsPage /> : baseSection === "review" ? <ReviewQueuePage /> : <MyAIPage />`. Replace with just `<MyAIPage doctorId={doctorId} />`.
3. Delete the import of `ReviewQueuePage` from this file.
4. Keep `PatientsPage` import (still rendered as overlay via `key.startsWith("patient")` path? No — `PatientsPage` is the LIST page, distinct from `PatientDetail`. The list is now reached via the overlay key `"patients"` itself — but that's a base path, not an overlay key.)

   **Correction:** `PatientsPage` will be rendered as a push subpage that LIVES at the route `/doctor/patients`. The cleanest approach: extend the `usePageStack` `renderContent` switch to handle the route `"/doctor/patients"` by returning `<PatientsPage />`. Look at how `key.startsWith("patient-")` returns `<PatientDetail />` (DoctorPage.jsx:403-405). Add a case for the bare patients list.

   Specifically: in the `renderContent` callback, before the `key.startsWith("patient-")` check, add:
   ```jsx
   if (key === "patients") {
     return <PatientsPage />;
   }
   ```
   Then verify that `usePageStack`'s key derivation produces `"patients"` for the `/doctor/patients` pathname. If not (e.g., it produces `"patients-"` or empty), adjust `usePageStack` itself or the key normalization in `DoctorPage`.

- [ ] **Step 4: Verify usePageStack key for `/doctor/patients`**

```bash
grep -n "overlayRouteKey\|sectionKey\|key" frontend/web/src/v2/usePageStack.js | head -20
```

Read the result and confirm what key the hook produces for `/doctor/patients`. Adjust the `renderContent` case in step 3 to match. (If key is something like `"section:patients"`, use that.)

- [ ] **Step 5: Run test to verify it passes**

```bash
cd frontend/web
npx vitest run src/v2/__tests__/single-tab-ia.test.jsx
```

Expected: PASS (3 tests now).

- [ ] **Step 6: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/DoctorPage.jsx frontend/web/src/v2/__tests__/single-tab-ia.test.jsx
git commit -m "refactor(v2): collapse DoctorPage baseSection to my-ai; PatientsPage becomes overlay"
```

---

## Task 4: Delete `ReviewQueuePage.jsx`

**Why:** Per spec, the queue list is removed — review work happens by drilling into `/doctor/review/:id` directly from the home triage row.

**Files:**
- Delete: `frontend/web/src/v2/pages/doctor/ReviewQueuePage.jsx`

- [ ] **Step 1: Verify no remaining imports**

```bash
grep -rn "ReviewQueuePage" frontend/web/src/
```

Expected output: no matches (we removed the import in Task 3). If matches remain, fix them before continuing.

- [ ] **Step 2: Delete the file**

```bash
rm frontend/web/src/v2/pages/doctor/ReviewQueuePage.jsx
```

- [ ] **Step 3: Verify build still compiles**

```bash
cd frontend/web
npx vite build --mode development 2>&1 | tail -20
```

Expected: build succeeds (or fails with unrelated errors — no missing-import errors mentioning `ReviewQueuePage`).

- [ ] **Step 4: Commit**

```bash
git add -A frontend/web/src/v2/pages/doctor/ReviewQueuePage.jsx
git commit -m "refactor(v2): delete ReviewQueuePage — queue list replaced by direct drill-in from home"
```

---

## Task 5: DoctorPage — simplify NavBar (always my-ai title + actions)

**Why:** With patients/review no longer base sections, the shell NavBar's conditional title and right-action are dead code. The shell always shows `我的AI` title and the FeedbackPopover + AddToDesktopPopover cluster.

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/DoctorPage.jsx`

- [ ] **Step 1: Edit NavBar JSX**

In `DoctorPage.jsx`, find the `<NavBar>` block (around lines 461-503).

Replace the conditional `right={...}` prop with the unconditional my-ai cluster:

```jsx
<NavBar
  backArrow={false}
  right={
    <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
      <FeedbackPopover>
        <div
          role="button"
          aria-label="反馈"
          style={{
            padding: 8,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
          }}
        >
          <FeedbackOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />
        </div>
      </FeedbackPopover>
      <AddToDesktopPopover />
    </div>
  }
  style={{
    "--height": "44px",
    "--border-bottom": `0.5px solid ${APP.border}`,
    backgroundColor: APP.surface,
    flexShrink: 0,
  }}
>
  我的AI
</NavBar>
```

- [ ] **Step 2: Run test suite**

```bash
cd frontend/web
npx vitest run src/v2/__tests__/single-tab-ia.test.jsx
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/DoctorPage.jsx
git commit -m "refactor(v2): simplify DoctorPage NavBar to always show my-ai title and actions"
```

---

## Task 6: MyAIPage — swap quickActions tile (新建病历 → 全部患者)

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/MyAIPage.jsx`

- [ ] **Step 1: Edit imports**

In `MyAIPage.jsx` imports section:
- Remove: `import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";`
- Add: `import PeopleAltOutlinedIcon from "@mui/icons-material/PeopleAltOutlined";`

- [ ] **Step 2: Edit `quickActions` array**

Find the array (around line 531-547). Replace the first entry:

```jsx
const quickActions = [
  {
    label: "全部患者",
    icon: <PeopleAltOutlinedIcon sx={{ fontSize: ICON.xl, color: APP.primary }} />,
    onClick: () => navigate(dp("patients")),
  },
  {
    label: "预问诊码",
    icon: <QrCodeScannerOutlinedIcon sx={{ fontSize: ICON.xl, color: APP.primary }} />,
    onClick: () => navigate(dp("settings/qr")),
  },
  {
    label: "知识库",
    icon: <MenuBookOutlinedIcon sx={{ fontSize: ICON.xl, color: APP.primary }} />,
    onClick: () => navigate(dp("settings/knowledge")),
  },
];
```

- [ ] **Step 3: Manually verify in browser**

Start the dev servers (no hot-reload):

```bash
cd frontend/web && npm run dev -- --no-hot &
cd ../.. && /Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 &
```

Open `http://localhost:5173/doctor/my-ai`. Confirm first tile reads "全部患者" with people icon.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/MyAIPage.jsx
git commit -m "feat(v2): replace 新建病历 quick-action tile with 全部患者"
```

---

## Task 7: MyAIPage — retarget "待审核诊断建议" triage row + delete "全部事项 ›" link

**Why:** With the queue list deleted, the row drills directly into the first pending review item. The redundant SectionHeader link goes away too (α decision).

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/MyAIPage.jsx`

- [ ] **Step 1: Locate `triageRows` and `useReviewQueue` data**

In `MyAIPage.jsx`, the `useReviewQueue` data is already in scope (search for `useReviewQueue` around line ~470). Find where it produces `pendingReview` count. The actual queue items should be available — confirm by reading the hook's return shape.

- [ ] **Step 2: Compute `firstPendingReviewId`**

Add near the existing `pendingReview` derivation:

```jsx
const firstPendingReviewId = (reviewQueue?.items || reviewQueue || [])
  .find((item) => item.status === "pending")?.id;
```

(Adjust the property access to match the actual hook return shape; the hook may return `data` directly, or a wrapped object.)

- [ ] **Step 3: Update `triageRows[0]` onClick**

Change the first triage row entry (around lines 498-508):

```jsx
{
  key: "review",
  label: "待审核诊断建议",
  description: `${pendingReview} 位患者待确认`,
  count: pendingReview,
  icon: PersonOutlineIcon,
  bg: APP.primaryLight,
  color: APP.primary,
  onClick: () => {
    if (firstPendingReviewId) {
      navigate(dp(`review-${firstPendingReviewId}`));
    }
  },
},
```

- [ ] **Step 4: Delete "全部事项 ›" SectionHeader prop**

Find the SectionHeader for 今日关注 (around lines 672-676):

```jsx
<SectionHeader
  title="今日关注"
  actionLabel="全部事项"
  onAction={() => navigate(`${dp("review")}?tab=pending`)}
/>
```

Change to:

```jsx
<SectionHeader title="今日关注" />
```

- [ ] **Step 5: Manually verify**

Restart frontend (or refresh page). Open `/doctor/my-ai` with a doctor account that has at least one pending review item. Confirm:
- Tapping the "待审核诊断建议" row navigates to the first pending item's review detail page (URL contains the record id).
- 今日关注 SectionHeader has no "全部事项 ›" link on the right.

- [ ] **Step 6: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/MyAIPage.jsx
git commit -m "feat(v2): triage row drills into first pending review item; drop redundant 全部事项 link"
```

---

## Task 8: PatientsPage — add own NavBar with back+home + title + "+"

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/PatientsPage.jsx`

- [ ] **Step 1: Add imports**

At the top of `PatientsPage.jsx`:

```jsx
import { NavBar } from "antd-mobile";
import SubpageBackHome from "../../components/SubpageBackHome";
import { AddCircleOutline } from "antd-mobile-icons";
```

(Verify `AddCircleOutline` isn't already imported — it might be.)

- [ ] **Step 2: Render NavBar at top of JSX**

In the main return statement, immediately inside the root `<div>` (or `pageContainer`-styled element), add:

```jsx
<NavBar
  backArrow={<SubpageBackHome />}
  onBack={() => {
    markIntentionalBack();
    navigate(-1);
  }}
  right={
    <div
      role="button"
      aria-label="新建病历"
      onClick={() => navigate(dp("patients?action=new"))}
      style={{
        padding: 8,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
      }}
    >
      <AddCircleOutline style={{ fontSize: ICON.md }} />
    </div>
  }
  style={{
    "--height": "44px",
    "--border-bottom": `0.5px solid ${APP.border}`,
    backgroundColor: APP.surface,
  }}
>
  患者
</NavBar>
```

Add `markIntentionalBack` to imports from `useNavDirection` if not already.

- [ ] **Step 3: Verify bottom safe-area**

Search PatientsPage for `SafeArea`:

```bash
grep -n "SafeArea" frontend/web/src/v2/pages/doctor/PatientsPage.jsx
```

If it has none, add `<SafeArea position="bottom" />` at the end of the scroll container. If it relies on a layout helper that includes it, leave alone.

- [ ] **Step 4: Manual verify**

Open `/doctor/patients`. Confirm:
- NavBar shows `[← 🏠]` on left, "患者" centered, `+` on right
- Tapping `+` opens the new-record picker
- Tapping `←` returns to home with slide animation
- Tapping 🏠 returns to home with slide animation

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/PatientsPage.jsx
git commit -m "feat(v2): PatientsPage owns its NavBar with back+home + title + new-record button"
```

---

## Task 9: MyAIPage — add bottom safe-area

**Why:** Replaces the bottom inset previously provided by the deleted TabBar's SafeArea.

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/MyAIPage.jsx`

- [ ] **Step 1: Add SafeArea**

In `MyAIPage.jsx`, find the closing `</div>` of the scroll container (the inner `<div style={{ ...scrollable, paddingTop: 12, paddingBottom: 16 }}>`). Just before it closes, add:

```jsx
<SafeArea position="bottom" />
```

Add `SafeArea` to the antd-mobile import at the top.

- [ ] **Step 2: Manual verify on home-indicator device**

Open `/doctor/my-ai` in a browser; resize to iPhone X dimensions. Confirm last visible row (likely 最近使用 last item) is not clipped by the home indicator.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/MyAIPage.jsx
git commit -m "feat(v2): MyAIPage renders own bottom SafeArea (replaces deleted TabBar inset)"
```

---

## Task 10: ReviewPage — auto-advance on finalize + back+home cluster

**Files:**
- Modify: `frontend/web/src/v2/pages/doctor/ReviewPage.jsx`
- Test: `frontend/web/src/v2/__tests__/single-tab-ia.test.jsx`

- [ ] **Step 1: Decide test surface for auto-advance**

The finalize handler is private to ReviewPage and triggered by an internal Button. Two options:

- **Unit-level:** extract the post-finalize navigation logic into a small helper `computeNextNav(reviewQueue, currentId, navigate)` that's pure and testable. Then write Vitest unit tests against the helper directly.
- **Manual-only:** skip Vitest and rely on the manual verification step (Step 5 below) plus the existing Playwright E2E smoke.

**Choose unit-level** unless extracting the helper triggers a cascade of changes inside ReviewPage. If so, fall back to manual-only and document in the commit message.

Helper to extract (write the test for it):

```jsx
// In a new file: frontend/web/src/v2/pages/doctor/reviewAutoAdvance.js
export function computeNextNav(queue, currentId) {
  const list = queue?.items || queue || [];
  const next = list.find((item) => item.status === "pending" && item.id !== currentId);
  const remaining = list.filter((item) => item.status === "pending" && item.id !== currentId).length;
  if (next) {
    return { kind: "next", nextId: next.id, remaining };
  }
  return { kind: "done" };
}
```

Test in `frontend/web/src/v2/pages/doctor/__tests__/reviewAutoAdvance.test.js`:

```js
import { describe, test, expect } from "vitest";
import { computeNextNav } from "../reviewAutoAdvance";

describe("computeNextNav", () => {
  test("returns next pending record id, excluding current", () => {
    const queue = [
      { id: "r1", status: "pending" },
      { id: "r2", status: "pending" },
      { id: "r3", status: "approved" },
    ];
    expect(computeNextNav(queue, "r1")).toEqual({ kind: "next", nextId: "r2", remaining: 1 });
  });

  test("returns done when no pending items remain", () => {
    const queue = [{ id: "r1", status: "pending" }];
    expect(computeNextNav(queue, "r1")).toEqual({ kind: "done" });
  });

  test("handles wrapped queue shape { items: [...] }", () => {
    const queue = { items: [{ id: "r1", status: "pending" }, { id: "r2", status: "pending" }] };
    expect(computeNextNav(queue, "r1")).toEqual({ kind: "next", nextId: "r2", remaining: 1 });
  });

  test("handles null/undefined queue", () => {
    expect(computeNextNav(null, "r1")).toEqual({ kind: "done" });
    expect(computeNextNav(undefined, "r1")).toEqual({ kind: "done" });
  });
});
```

- [ ] **Step 2: Run helper test to verify it fails**

```bash
cd frontend/web
npx vitest run src/v2/pages/doctor/__tests__/reviewAutoAdvance.test.js
```

Expected: FAIL with "Cannot find module '../reviewAutoAdvance'".

- [ ] **Step 3: Create the helper module**

Create `frontend/web/src/v2/pages/doctor/reviewAutoAdvance.js` with the `computeNextNav` function from Step 1 above.

Run the test again — expected: PASS (4 tests).

- [ ] **Step 4: Implement auto-advance in ReviewPage**

In `ReviewPage.jsx`:

1. Verify `useReviewQueue` is already imported (it should be — check the import block). If not: `import { useReviewQueue } from "../../../lib/doctorQueries";`.
2. Add the helper import: `import { computeNextNav } from "./reviewAutoAdvance";`.
3. Inside the component, get `reviewQueue`:
   ```jsx
   const { data: reviewQueue } = useReviewQueue(doctorId);
   ```
4. Find the post-finalize navigation block (around lines 1296-1310). Replace the `setTimeout(() => { ... })` body:

```jsx
setTimeout(() => {
  if (isPreviewOnboardingFlow && followUpTaskIds.length > 0) {
    const highlight = followUpTaskIds.join(",");
    navigate(`${dp("tasks")}?tab=followups&highlight_task_ids=${highlight}&origin=review_finalize`);
    return;
  }
  const decision = computeNextNav(reviewQueue, record.id);
  if (decision.kind === "next") {
    Toast.show({ content: `继续下一项 (剩余 ${decision.remaining} 项)`, position: "bottom" });
    navigate(dp(`review-${decision.nextId}`), { replace: true });
  } else {
    Toast.show({ content: "已处理完今日全部事项", position: "bottom" });
    navigate(dp("my-ai"));
  }
}, 600);
```

If the actual property name on a queue item is not `id` (e.g., it's `record_id`), fix that in BOTH `reviewAutoAdvance.js` and the test before continuing. Grep `frontend/web/src/lib/doctorQueries.js` for `useReviewQueue` to see the canonical shape.

- [ ] **Step 3: Update NavBar with back+home cluster**

Find the existing `<NavBar backArrow={<LeftOutline />} ...>` (around line ~1438 or ~1457). Replace the `backArrow` value with `<SubpageBackHome />` and add the import:

```jsx
import SubpageBackHome from "../../components/SubpageBackHome";
```

Remove the `LeftOutline` import if no longer used in this file.

- [ ] **Step 4: Run test**

```bash
cd frontend/web
npx vitest run src/v2/__tests__/single-tab-ia.test.jsx
```

Expected: PASS for whatever auto-advance tests are implemented.

- [ ] **Step 5: Manual verify**

Open `/doctor/review/<some-pending-id>`. Finalize. Confirm:
- If another pending item exists: navigate to that item, Toast shows remaining count
- If queue empty: navigate to `/doctor/my-ai`, Toast shows "已处理完今日全部事项"

- [ ] **Step 6: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/ReviewPage.jsx frontend/web/src/v2/pages/doctor/reviewAutoAdvance.js frontend/web/src/v2/pages/doctor/__tests__/reviewAutoAdvance.test.js
git commit -m "feat(v2): ReviewPage auto-advances to next pending item; back+home cluster"
```

---

## Task 11: Sweep — apply `SubpageBackHome` to all remaining doctor subpages

**Why:** Per spec, every doctor-app push subpage NavBar gets the back+home cluster. Mechanical change.

**Files (each gets one edit):**
- `frontend/web/src/v2/pages/doctor/PatientDetail.jsx`
- `frontend/web/src/v2/pages/doctor/PatientChatPage.jsx`
- `frontend/web/src/v2/pages/doctor/SettingsPage.jsx`
- `frontend/web/src/v2/pages/doctor/OnboardingWizard.jsx`
- `frontend/web/src/v2/pages/doctor/settings/PersonaSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/KnowledgeSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/AddKnowledgeSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/KnowledgeDetailSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/AboutSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/TeachByExampleSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/PendingReviewSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/PersonaOnboardingSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/TemplateSubpage.jsx`
- `frontend/web/src/v2/pages/doctor/settings/QrSubpage.jsx`

- [ ] **Step 1: For each file in the list above:**

For each file, locate its `<NavBar backArrow={...}>` line and:

1. Replace the `backArrow` value with `<SubpageBackHome />`.
2. Add `import SubpageBackHome from "<correct relative path>/components/SubpageBackHome";` to the imports. The path depends on file depth:
   - Files in `pages/doctor/`: `"../../components/SubpageBackHome"`
   - Files in `pages/doctor/settings/`: `"../../../components/SubpageBackHome"`
3. If `LeftOutline` is no longer used in the file, remove its import.

For `OnboardingWizard.jsx` specifically: it uses `backArrow={step > 1}` (a boolean). For step 1, leave `backArrow={false}`; for step > 1, use `backArrow={<SubpageBackHome />}`. The home icon is meaningful even from step 2+ as a quick exit.

- [ ] **Step 2: Run lint**

```bash
cd frontend/web
bash ../../scripts/lint-ui.sh
```

Expected: passes (no token violations introduced).

- [ ] **Step 3: Smoke test in browser**

Visit each page in a browser and confirm `[← 🏠]` cluster appears in the NavBar. Quick checklist:
- `/doctor/patients/<some-id>` (PatientDetail)
- `/doctor/patients/<some-id>/chat` (PatientChatPage)
- `/doctor/settings` (SettingsPage)
- `/doctor/settings/persona` (PersonaSubpage)
- `/doctor/settings/knowledge` (KnowledgeSubpage)
- `/doctor/settings/about` (AboutSubpage)
- `/doctor/settings/qr` (QrSubpage)
- `/doctor/settings/template` (TemplateSubpage)
- `/doctor/settings/teach` (TeachByExampleSubpage)
- One of the lesser-used: KnowledgeDetailSubpage, AddKnowledgeSubpage, PendingReviewSubpage, PersonaOnboardingSubpage

Tap the home icon on at least 3 different pages — each should slide back to `/doctor/my-ai`.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/
git commit -m "refactor(v2): apply SubpageBackHome cluster to all doctor-app push subpages"
```

---

## Task 12: App.jsx — cold-start deep-link history seed

**Files:**
- Modify: `frontend/web/src/v2/App.jsx`
- Test: `frontend/web/src/v2/__tests__/single-tab-ia.test.jsx`

- [ ] **Step 1: Extract the seed logic into a testable function**

Create `frontend/web/src/v2/coldStartSeed.js`:

```js
/**
 * Decide whether to seed a synthetic /doctor/my-ai history entry behind a
 * deep-link entry URL, so back-tap from the deep link unwinds to home
 * instead of exiting the app.
 *
 * Returns one of:
 *   { kind: "noop" }                  — don't seed (already at home, not a doctor path, or has history)
 *   { kind: "seed", homePath, target } — seed home then re-push target
 */
export function decideColdStartSeed({ pathname, search, hash, historyLength }) {
  const isDoctorPath = pathname.startsWith("/doctor/") || pathname.startsWith("/mock/doctor/");
  const isHome = pathname === "/doctor/my-ai" || pathname === "/mock/doctor/my-ai";
  if (!isDoctorPath || isHome || historyLength > 1) {
    return { kind: "noop" };
  }
  const homePath = pathname.startsWith("/mock/") ? "/mock/doctor/my-ai" : "/doctor/my-ai";
  return { kind: "seed", homePath, target: pathname + search + hash };
}
```

- [ ] **Step 2: Write failing test**

Create `frontend/web/src/v2/__tests__/coldStartSeed.test.js`:

```js
import { describe, test, expect } from "vitest";
import { decideColdStartSeed } from "../coldStartSeed";

describe("decideColdStartSeed", () => {
  test("noop when at home", () => {
    expect(decideColdStartSeed({
      pathname: "/doctor/my-ai", search: "", hash: "", historyLength: 1,
    })).toEqual({ kind: "noop" });
  });

  test("noop when not a doctor path", () => {
    expect(decideColdStartSeed({
      pathname: "/login", search: "", hash: "", historyLength: 1,
    })).toEqual({ kind: "noop" });
  });

  test("noop when history already has multiple entries", () => {
    expect(decideColdStartSeed({
      pathname: "/doctor/review/abc", search: "", hash: "", historyLength: 5,
    })).toEqual({ kind: "noop" });
  });

  test("seeds /doctor/my-ai for cold-start /doctor/review/:id", () => {
    expect(decideColdStartSeed({
      pathname: "/doctor/review/abc", search: "?x=1", hash: "", historyLength: 1,
    })).toEqual({
      kind: "seed",
      homePath: "/doctor/my-ai",
      target: "/doctor/review/abc?x=1",
    });
  });

  test("seeds /mock/doctor/my-ai for cold-start /mock/doctor/patients/123", () => {
    expect(decideColdStartSeed({
      pathname: "/mock/doctor/patients/123", search: "", hash: "", historyLength: 1,
    })).toEqual({
      kind: "seed",
      homePath: "/mock/doctor/my-ai",
      target: "/mock/doctor/patients/123",
    });
  });

  test("preserves search and hash in the target", () => {
    expect(decideColdStartSeed({
      pathname: "/doctor/patients/9",
      search: "?tab=records",
      hash: "#section-2",
      historyLength: 1,
    })).toEqual({
      kind: "seed",
      homePath: "/doctor/my-ai",
      target: "/doctor/patients/9?tab=records#section-2",
    });
  });
});
```

- [ ] **Step 3: Run test**

```bash
cd frontend/web
npx vitest run src/v2/__tests__/coldStartSeed.test.js
```

Expected: PASS (6 tests).

- [ ] **Step 4: Wire the seed into App.jsx**

In `frontend/web/src/v2/App.jsx`, find the closest router-aware component that wraps the doctor routes (likely `App` itself or a `DoctorRoute` wrapper — check imports for `useNavigate`). Add a mount-only effect:

```jsx
import { decideColdStartSeed } from "./coldStartSeed";

// Inside the component:
useEffect(() => {
  const decision = decideColdStartSeed({
    pathname: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash,
    historyLength: window.history.length,
  });
  if (decision.kind === "seed") {
    navigate(decision.homePath, { replace: true });
    navigate(decision.target, { replace: false });
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

If the existing `App.jsx` doesn't have `useNavigate` access at the right level, hoist the effect into the component that does (most likely the immediate child of `<BrowserRouter>`).

- [ ] **Step 5: Manual verify**

In a fresh tab (so history is empty):
1. Navigate directly to `http://localhost:5173/doctor/review/<id>`.
2. After page loads, click the back arrow in the NavBar.
3. Expected: lands on `/doctor/my-ai` (not browser exit / blank tab).

Repeat with `http://localhost:5173/doctor/patients/<id>` — same behavior.

- [ ] **Step 6: Commit**

```bash
git add frontend/web/src/v2/App.jsx frontend/web/src/v2/coldStartSeed.js frontend/web/src/v2/__tests__/coldStartSeed.test.js
git commit -m "feat(v2): seed /doctor/my-ai history entry on cold-start deep links"
```

---

## Task 13: Tests — back-stack unwinding, ?action=new, /mock path coverage

**Why:** Codex's test list — fill the remaining gaps.

**Files:**
- Modify: `frontend/web/src/v2/__tests__/single-tab-ia.test.jsx`

- [ ] **Step 1: Add a helper hook to expose router state inside tests**

At the top of `single-tab-ia.test.jsx` (or in a shared test helper):

```jsx
import { useNavigate, useLocation } from "react-router-dom";
import { renderHook, act } from "@testing-library/react";

function useRouter() {
  const navigate = useNavigate();
  const location = useLocation();
  return { navigate, location };
}

function renderHostWithRouter(initialPath = "/doctor/my-ai") {
  const wrapper = ({ children }) => (
    <Host initialPath={initialPath}>{children}</Host>
  );
  return renderHook(() => useRouter(), { wrapper });
}
```

This gives tests programmatic `navigate(...)` access while keeping the full `Host` provider stack mounted.

- [ ] **Step 2: Add tests**

Append to `single-tab-ia.test.jsx`:

```jsx
describe("Single-tab IA — back-stack and routing", () => {
  test("home → patients → back returns to home", () => {
    const { result } = renderHostWithRouter("/doctor/my-ai");
    act(() => result.current.navigate("/doctor/patients"));
    expect(result.current.location.pathname).toBe("/doctor/patients");
    act(() => result.current.navigate(-1));
    expect(result.current.location.pathname).toBe("/doctor/my-ai");
  });

  test("home → review/r1 → back returns to home", () => {
    const { result } = renderHostWithRouter("/doctor/my-ai");
    act(() => result.current.navigate("/doctor/review/r1"));
    expect(result.current.location.pathname).toBe("/doctor/review/r1");
    act(() => result.current.navigate(-1));
    expect(result.current.location.pathname).toBe("/doctor/my-ai");
  });

  test("?action=new is cleaned from URL by PatientsPage useEffect", async () => {
    const { result } = renderHostWithRouter("/doctor/patients?action=new");
    // PatientsPage cleans the query param via navigate(..., { replace: true })
    // Wait for the cleanup effect to run.
    await new Promise((r) => setTimeout(r, 0));
    expect(result.current.location.search).not.toContain("action=new");
  });

  test("/mock/doctor/my-ai mounts the same root content as /doctor/my-ai", () => {
    // Hero banner title is a stable text marker rendered by MyAIPage
    const r1 = render(<Host initialPath="/doctor/my-ai" />);
    expect(r1.queryByText(/您的专属医疗AI助手/)).toBeInTheDocument();
    r1.unmount();

    const r2 = render(<Host initialPath="/mock/doctor/my-ai" />);
    expect(r2.queryByText(/您的专属医疗AI助手/)).toBeInTheDocument();
  });
});
```

The hero banner text "您的专属医疗AI助手" lives in `MyAIPage.jsx:615` (`<HeroBanner title="您的专属医疗AI助手" .../>`) — stable across single-tab refactor.

- [ ] **Step 2: Run all single-tab-ia tests**

```bash
cd frontend/web
npx vitest run src/v2/__tests__/single-tab-ia.test.jsx
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/__tests__/single-tab-ia.test.jsx
git commit -m "test(v2): single-tab IA back-stack, ?action=new, /mock path coverage"
```

---

## Task 14: Audit Playwright E2E selectors

**Files:**
- Modify: any test under `frontend/web/tests/` that targets the TabBar

- [ ] **Step 1: Search for tab-targeting selectors**

```bash
grep -rn "adm-tab-bar\|getByRole.*tab\|click.*tab\|TabBar" frontend/web/tests/ 2>/dev/null
```

- [ ] **Step 2: Replace each match**

For each test that clicks a TabBar item:
- If it was tapping `审核` → replace with `page.goto('/doctor/review/<id>')` directly (or click the home triage row that navigates there).
- If it was tapping `患者` → click the `全部患者` quick-action tile on home, OR `page.goto('/doctor/patients')`.
- If it was tapping `我的AI` → already on home; just remove the click.

If no E2E tests target the TabBar, skip this task (commit nothing).

- [ ] **Step 3: Run E2E if changes were made**

```bash
cd frontend/web
rm -rf test-results
npx playwright test
```

- [ ] **Step 4: Commit**

```bash
git add frontend/web/tests/
git commit -m "test(e2e): replace TabBar-tap selectors with route-based navigation"
```

(Skip if no changes.)

---

## Task 15: Final verification & lint pass

- [ ] **Step 1: Run lint-ui**

```bash
bash scripts/lint-ui.sh
```

Expected: 0 violations.

- [ ] **Step 2: Run all Vitest tests**

```bash
cd frontend/web
npx vitest run
```

Expected: all pass (existing 3 baseline + new tests added in this plan).

- [ ] **Step 3: Run E2E gate (if servers can run)**

```bash
cd frontend/web
rm -rf test-results
npx playwright test
```

Expected: all pass.

- [ ] **Step 4: Manual checklist (from spec)**

Walk through every box in the spec's "Manual verification checklist" section. For each:
- [ ] `/doctor/my-ai` renders without TabBar at bottom
- [ ] First tile reads "全部患者" with people icon, taps → `/doctor/patients`
- [ ] Second tile "预问诊码" → `/doctor/settings/qr`
- [ ] Third tile "知识库" → `/doctor/settings/knowledge`
- [ ] 今日关注 row "待审核诊断建议" drills into first pending review item directly
- [ ] On finalize, ReviewPage advances to next pending review item; on last item, returns to `/doctor/my-ai` with Toast
- [ ] 今日关注 SectionHeader has no "全部事项 ›" link
- [ ] 最近使用 row taps still open patient detail / knowledge detail
- [ ] PatientsPage NavBar shows `[← 🏠]` + 患者 title + `+` button
- [ ] PatientsPage `+` opens the new-record picker
- [ ] Home icon (🏠) on PatientsPage navigates to `/doctor/my-ai` with slide animation
- [ ] Home icon on PatientDetail (2-level deep) returns to `/doctor/my-ai` in one tap
- [ ] Home icon on ReviewPage navigates to `/doctor/my-ai` with slide animation
- [ ] Home icon on every settings subpage navigates to `/doctor/my-ai`
- [ ] Tapping home icon does NOT also fire the back arrow
- [ ] Back from PatientsPage returns to `/doctor/my-ai` with slide animation
- [ ] WeChat push deep link to `/doctor/review/:id` cold-start: tap back → lands on `/doctor/my-ai`, does not exit
- [ ] WeChat ← arrow / hardware back: still no slide animation
- [ ] Bottom inset visible on iPhone X-class devices on home, patient list, review detail
- [ ] No clipped last rows on any scrollable surface
- [ ] No console warnings about removed icon imports

- [ ] **Step 5: If all green, the plan is complete**

No final commit needed — every task already committed.

---

## Out-of-scope notes

These were considered and explicitly deferred:

- **Patient-portal pages** (`PatientPrivacySubpage`, `PatientTaskDetailPage`, etc.) — separate IA, not in this scope.
- **Instrumentation** — user chose to ship blind.
- **Feature flag** — user chose hard cut despite codex's pushback.
- **`ReviewSubpage.jsx`** in settings/ folder — already orphaned per DoctorPage comment "ReviewSubpage is a presentational component that expects props" and the legacy redirect at DoctorPage.jsx:420-422. No change.
- **`TaskDetailSubpage.jsx`** — exists but not in TabBar / shell; if it has its own NavBar, it inherits the home-icon sweep treatment when reachable. Confirm during Task 11 sweep whether it has a NavBar.

---

## If something fails

If a task's verification step fails:

1. **Read the actual error** before acting. Look at console output, test failure message, or browser console.
2. **Don't skip the verify step** — partial impl + green commit poisons later tasks.
3. **If blocked > 15 min** on the same task, escalate: revert that task's commit, write a one-line summary of what's blocking, and stop. Do NOT keep poking.
4. **Cold-start seed + back-stack tests** are the highest-risk piece. If they're flaky in jsdom, prefer Playwright integration coverage over Vitest unit coverage for those specific cases — note in the commit and add to the manual checklist instead.

---

## Acceptance

The PR is ready when:
1. All Vitest tests pass (`npx vitest run`).
2. Lint passes (`bash scripts/lint-ui.sh`).
3. Every box in Task 15 Step 4's manual checklist is checked.
4. WeChat cold-start deep-link back behavior is verified on a real device or in a dev tools simulation.

If a single critical regression appears post-ship (e.g., WeChat back-tap exits app despite the seed), the rollback is `git revert <PR-merge-commit>`.
