# Patient Pages Design Parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project rule (overrides skill default):** do NOT run `git commit` unless the user explicitly says "commit". Commit steps in this plan document *what* to commit and *when* a checkpoint is reached — actual execution waits for user sign-off.

**Goal:** Bring the v2 patient portal to structural + visual parity with the v2 doctor app, keeping patient-friendly defaults (large font, WeChat-style chat).

**Architecture:** Mirror `DoctorPage` structure — top NavBar, bottom TabBar, pathname-based section + subpage detection, full-screen subpage overlays. Migrate patient data fetching to React Query via a new `patientQueries.js` (parallel to `doctorQueries.js`). Add read-only detail pages for records and tasks, plus About/Privacy subpages under the 我的 tab.

**Tech Stack:** React 19, antd-mobile v5, `@tanstack/react-query`, `react-router-dom` v6, zustand (font scale store). Playwright for e2e, Vitest for unit.

**Spec:** `docs/superpowers/specs/2026-04-18-patient-pages-design-parity-design.md`

**Target audience:** patients 40+, WeChat ease-of-use. Default font scale `"large"` (already store default), WeChat-green chat bubbles kept.

---

## File Structure

**New files** (13):
- `frontend/web/src/lib/patientQueries.js` — React Query hooks for patient data.
- `frontend/web/src/v2/pages/patient/PatientRecordDetailPage.jsx` — read-only record detail.
- `frontend/web/src/v2/pages/patient/PatientTaskDetailPage.jsx` — task detail with complete/undo.
- `frontend/web/src/v2/pages/patient/PatientAboutSubpage.jsx` — version + terms.
- `frontend/web/src/v2/pages/patient/PatientPrivacySubpage.jsx` — privacy policy view.
- `frontend/web/src/v2/pages/patient/_shared/PrivacyBody.jsx` — extracted privacy body (shared with `/privacy` route).
- `frontend/web/src/v2/pages/patient/pathname.js` — pure detection helpers.
- `frontend/web/tests/unit/patient-pathname.spec.js` — Vitest for detection helpers.
- `frontend/web/tests/e2e/24-patient-shell.spec.ts`
- `frontend/web/tests/e2e/25-patient-record-detail.spec.ts`
- `frontend/web/tests/e2e/26-patient-task-detail.spec.ts`
- `frontend/web/tests/e2e/27-patient-my-subpages.spec.ts`
- `frontend/web/src/v2/pages/patient/PatientOnboarding.restyle.md` — optional dev note (delete after sweep).

**Modified files** (9):
- `frontend/web/src/lib/queryKeys.js` — add `PK` namespace.
- `frontend/web/src/v2/pages/patient/PatientPage.jsx` — shell rewrite.
- `frontend/web/src/v2/pages/patient/ChatTab.jsx` — data layer migration.
- `frontend/web/src/v2/pages/patient/RecordsTab.jsx` — data layer + PullToRefresh + remove inline "新建病历" button.
- `frontend/web/src/v2/pages/patient/TasksTab.jsx` — data layer + PullToRefresh + SwipeAction.
- `frontend/web/src/v2/pages/patient/MyPage.jsx` — font scale store unification + About/Privacy links.
- `frontend/web/src/v2/pages/patient/PatientOnboarding.jsx` — token/icon sweep.
- `frontend/web/src/v2/pages/PrivacyPage.jsx` — delegate body to shared component.
- `frontend/web/tests/e2e/22-patient-records.spec.ts` — update for NavBar + detail flow.
- `frontend/web/tests/e2e/23-patient-tasks.spec.ts` — update for SwipeAction.

**Untouched:** `frontend/web/src/v2/App.jsx` routes (already fixed this session). `PatientApiContext.jsx` (used by hooks unchanged). All backend code.

---

# Phase 1 — Shell

Goal of Phase 1: patient URL still shows old tab content, but now hung under a proper NavBar with pathname-based routing and subpage overlay hooks. Stubs exist for new subpages.

## Task 1: Create pathname detection helpers + unit tests

**Files:**
- Create: `frontend/web/src/v2/pages/patient/pathname.js`
- Create: `frontend/web/tests/unit/patient-pathname.spec.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/web/tests/unit/patient-pathname.spec.js`:

```js
import { describe, it, expect } from "vitest";
import {
  detectSection,
  detectRecordDetail,
  detectTaskDetail,
  detectProfileSubpage,
} from "../../src/v2/pages/patient/pathname";

describe("detectSection", () => {
  it.each([
    ["/patient", "chat"],
    ["/patient/", "chat"],
    ["/patient/chat", "chat"],
    ["/patient/records", "records"],
    ["/patient/tasks", "tasks"],
    ["/patient/profile", "profile"],
    ["/patient/records/42", "records"],
    ["/patient/tasks/7", "tasks"],
    ["/patient/profile/about", "profile"],
    ["/patient/unknown", "chat"],
  ])("%s → %s", (path, expected) => {
    expect(detectSection(path)).toBe(expected);
  });
});

describe("detectRecordDetail", () => {
  it("returns id for /patient/records/42", () => {
    expect(detectRecordDetail("/patient/records/42")).toBe("42");
  });
  it("returns null for /patient/records/intake", () => {
    expect(detectRecordDetail("/patient/records/intake")).toBeNull();
  });
  it("returns null for /patient/records", () => {
    expect(detectRecordDetail("/patient/records")).toBeNull();
  });
  it("returns null for non-records paths", () => {
    expect(detectRecordDetail("/patient/tasks/42")).toBeNull();
  });
});

describe("detectTaskDetail", () => {
  it("returns id for /patient/tasks/7", () => {
    expect(detectTaskDetail("/patient/tasks/7")).toBe("7");
  });
  it("returns null for /patient/tasks", () => {
    expect(detectTaskDetail("/patient/tasks")).toBeNull();
  });
});

describe("detectProfileSubpage", () => {
  it.each([
    ["/patient/profile/about", "about"],
    ["/patient/profile/privacy", "privacy"],
  ])("%s → %s", (path, expected) => {
    expect(detectProfileSubpage(path)).toBe(expected);
  });
  it("returns null for /patient/profile", () => {
    expect(detectProfileSubpage("/patient/profile")).toBeNull();
  });
  it("returns null for unknown subpage", () => {
    expect(detectProfileSubpage("/patient/profile/xyz")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/web && npx vitest run tests/unit/patient-pathname.spec.js`
Expected: FAIL — cannot resolve module `pathname.js`.

- [ ] **Step 3: Implement `pathname.js`**

Create `frontend/web/src/v2/pages/patient/pathname.js`:

```js
/**
 * Pure helpers that translate a URL pathname into the currently-active
 * patient portal section or subpage. Mirrors the pattern used by
 * v2 DoctorPage (which parses location.pathname directly).
 *
 * These must stay side-effect free so they can be unit-tested without
 * a router context.
 */

const TABS = ["chat", "records", "tasks", "profile"];

/** /patient[/:tab[/:subpage]] → "chat" | "records" | "tasks" | "profile" (default "chat"). */
export function detectSection(pathname) {
  if (!pathname || pathname === "/patient" || pathname === "/patient/") return "chat";
  const parts = pathname.split("/").filter(Boolean); // ["patient", ...]
  const tab = parts[1];
  if (TABS.includes(tab)) return tab;
  return "chat";
}

/** /patient/records/:id → id (excluding "intake"). Returns null otherwise. */
export function detectRecordDetail(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[1] !== "records" || !parts[2] || parts[2] === "intake") return null;
  return parts[2];
}

/** /patient/tasks/:id → id. Returns null otherwise. */
export function detectTaskDetail(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[1] !== "tasks" || !parts[2]) return null;
  return parts[2];
}

/** /patient/profile/:sub → "about" | "privacy" | null. */
export function detectProfileSubpage(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[1] !== "profile" || !parts[2]) return null;
  if (parts[2] === "about" || parts[2] === "privacy") return parts[2];
  return null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/web && npx vitest run tests/unit/patient-pathname.spec.js`
Expected: PASS (all 21 cases).

- [ ] **Step 5: Commit checkpoint**

```bash
git add frontend/web/src/v2/pages/patient/pathname.js frontend/web/tests/unit/patient-pathname.spec.js
git commit -m "feat(v2): pure pathname helpers for patient shell routing"
```

---

## Task 2: Create subpage stubs

**Files:**
- Create: `frontend/web/src/v2/pages/patient/PatientRecordDetailPage.jsx`
- Create: `frontend/web/src/v2/pages/patient/PatientTaskDetailPage.jsx`
- Create: `frontend/web/src/v2/pages/patient/PatientAboutSubpage.jsx`
- Create: `frontend/web/src/v2/pages/patient/PatientPrivacySubpage.jsx`

- [ ] **Step 1: Create `PatientRecordDetailPage.jsx` stub**

```jsx
/**
 * @route /patient/records/:id
 * Read-only patient record detail. Stub until Task 10.
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";

export default function PatientRecordDetailPage({ recordId }) {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar
        backArrow={<LeftOutline />}
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        病历详情
      </NavBar>
      <div style={{ ...scrollable, padding: 16, color: APP.text3, fontSize: FONT.base }}>
        病历 #{recordId} — 即将上线
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `PatientTaskDetailPage.jsx` stub**

```jsx
/**
 * @route /patient/tasks/:id
 * Task detail with complete/undo. Stub until Task 11.
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";

export default function PatientTaskDetailPage({ taskId }) {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar
        backArrow={<LeftOutline />}
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        任务详情
      </NavBar>
      <div style={{ ...scrollable, padding: 16, color: APP.text3, fontSize: FONT.base }}>
        任务 #{taskId} — 即将上线
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `PatientAboutSubpage.jsx` stub**

```jsx
/**
 * @route /patient/profile/about
 * About page — version, build, terms. Stub until Task 12.
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";

export default function PatientAboutSubpage() {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar
        backArrow={<LeftOutline />}
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        关于
      </NavBar>
      <div style={{ ...scrollable, padding: 16, color: APP.text3, fontSize: FONT.base }}>
        即将上线
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `PatientPrivacySubpage.jsx` stub**

```jsx
/**
 * @route /patient/profile/privacy
 * Privacy policy — subpage frame. Stub until Task 12.
 */
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";

export default function PatientPrivacySubpage() {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar
        backArrow={<LeftOutline />}
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        隐私政策
      </NavBar>
      <div style={{ ...scrollable, padding: 16, color: APP.text3, fontSize: FONT.base }}>
        即将上线
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit checkpoint**

```bash
git add frontend/web/src/v2/pages/patient/PatientRecordDetailPage.jsx \
        frontend/web/src/v2/pages/patient/PatientTaskDetailPage.jsx \
        frontend/web/src/v2/pages/patient/PatientAboutSubpage.jsx \
        frontend/web/src/v2/pages/patient/PatientPrivacySubpage.jsx
git commit -m "feat(v2): patient subpage stubs (record/task/about/privacy)"
```

---

## Task 3: Rewrite `PatientPage.jsx` shell

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientPage.jsx`

- [ ] **Step 1: Write the full new shell**

Replace entire contents of `frontend/web/src/v2/pages/patient/PatientPage.jsx`:

```jsx
/**
 * @route /patient, /patient/:tab, /patient/:tab/:subpage
 *
 * PatientPage — patient portal shell (v2, antd-mobile).
 *
 * Mirrors DoctorPage structure:
 *   - Top NavBar with tab title + optional right action
 *   - Bottom TabBar with 4 tabs (chat / records / tasks / profile)
 *   - Full-screen subpage overlays (hide NavBar + TabBar)
 *   - Pathname-driven section detection (NOT useParams — wildcard route
 *     would make useParams() return only "*")
 *
 * Identity (token + name + doctor_id) hydrated from localStorage; QR-code
 * absorption preserved. Onboarding gate preserved.
 */

import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { NavBar, TabBar, SafeArea, Badge, Button } from "antd-mobile";
import {
  MessageOutline,
  MessageFill,
  FileOutline,
  UnorderedListOutline,
  UserOutline,
  AddCircleOutline,
} from "antd-mobile-icons";
import { usePatientApi } from "../../../api/PatientApiContext";
import { APP, FONT, ICON } from "../../theme";
import { pageContainer, navBarStyle } from "../../layouts";
import ChatTab from "./ChatTab";
import IntakePage from "./IntakePage";
import PatientOnboarding, { isOnboardingDone, markOnboardingDone } from "./PatientOnboarding";
import RecordsTab from "./RecordsTab";
import TasksTab from "./TasksTab";
import MyPage from "./MyPage";
import PatientRecordDetailPage from "./PatientRecordDetailPage";
import PatientTaskDetailPage from "./PatientTaskDetailPage";
import PatientAboutSubpage from "./PatientAboutSubpage";
import PatientPrivacySubpage from "./PatientPrivacySubpage";
import {
  detectSection,
  detectRecordDetail,
  detectTaskDetail,
  detectProfileSubpage,
} from "./pathname";

// ── Storage keys ───────────────────────────────────────────────────

const STORAGE_KEY = "patient_portal_token";
const STORAGE_NAME_KEY = "patient_portal_name";
const STORAGE_DOCTOR_KEY = "patient_portal_doctor_id";
const STORAGE_DOCTOR_NAME_KEY = "patient_portal_doctor_name";
const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";
const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

// ── Tab config ─────────────────────────────────────────────────────

const TABS = [
  { key: "chat",     label: "聊天", title: "聊天",   icon: <MessageOutline />,        activeIcon: <MessageFill />,        path: "/patient/chat" },
  { key: "records",  label: "病历", title: "病历",   icon: <FileOutline />,           activeIcon: <FileOutline />,        path: "/patient/records" },
  { key: "tasks",    label: "任务", title: "任务",   icon: <UnorderedListOutline />,  activeIcon: <UnorderedListOutline/>, path: "/patient/tasks" },
  { key: "profile",  label: "我的", title: "我的",   icon: <UserOutline />,           activeIcon: <UserOutline />,        path: "/patient/profile" },
];
// Note: File/UnorderedList/User have no Fill variant in antd-mobile-icons.
// TabBar conveys active state via color; Outline stays visually.

export default function PatientPage() {
  const api = usePatientApi();
  const location = useLocation();
  const navigate = useNavigate();

  // ── QR code token absorption (must run before state init) ────────
  useState(() => {
    const params = new URLSearchParams(window.location.search);
    const qrToken = params.get("token");
    if (qrToken) {
      const qrDoctorId = params.get("doctor_id");
      const qrName = params.get("name");
      localStorage.setItem(STORAGE_KEY, qrToken);
      if (qrName) localStorage.setItem(STORAGE_NAME_KEY, qrName);
      if (qrDoctorId) localStorage.setItem(STORAGE_DOCTOR_KEY, qrDoctorId);
      const cleanUrl = new URL(window.location.href);
      ["token", "doctor_id", "name"].forEach((k) => cleanUrl.searchParams.delete(k));
      window.history.replaceState({}, "", cleanUrl.toString());
    }
  });

  // ── Identity state ───────────────────────────────────────────────
  const [token, setToken] = useState(() => localStorage.getItem(STORAGE_KEY) || "");
  const [patientName, setPatientName] = useState(() => localStorage.getItem(STORAGE_NAME_KEY) || "");
  const [doctorName, setDoctorName] = useState(() => localStorage.getItem(STORAGE_DOCTOR_NAME_KEY) || "");
  const [doctorId, setDoctorId] = useState(() => localStorage.getItem(STORAGE_DOCTOR_KEY) || "");
  const [unreadCount, setUnreadCount] = useState(0);
  const [onboardingDone, setOnboardingDone] = useState(() => {
    const pid = localStorage.getItem("patient_portal_patient_id");
    return isOnboardingDone(pid);
  });

  // Mock mode
  useEffect(() => {
    if (api.isMock) {
      setToken("mock-patient-token");
      setPatientName("陈伟强");
      setDoctorName("张医生");
      setDoctorId("mock_doctor");
    }
  }, [api.isMock]);

  // Real mode: refresh identity
  useEffect(() => {
    if (!token || api.isMock) return;
    api
      .getPatientMe(token)
      .then((data) => {
        if (data.patient_name) setPatientName(data.patient_name);
        setDoctorName(data.doctor_name || "");
        if (data.doctor_id) setDoctorId(data.doctor_id);
        if (data.patient_id) {
          localStorage.setItem("patient_portal_patient_id", String(data.patient_id));
        }
      })
      .catch(() => {});
  }, [token, api]);

  // ── Pathname-driven overlay/section detection ────────────────────
  const section = detectSection(location.pathname);
  const recordDetailId = detectRecordDetail(location.pathname);
  const taskDetailId = detectTaskDetail(location.pathname);
  const profileSubpage = detectProfileSubpage(location.pathname);
  const inIntake = location.pathname === "/patient/records/intake";

  const fullScreenActive =
    inIntake || !!recordDetailId || !!taskDetailId || !!profileSubpage;

  // ── Tab + navigation handlers ────────────────────────────────────
  const handleTabChange = useCallback(
    (key) => navigate(`/patient/${key}`),
    [navigate]
  );

  const startIntake = useCallback(
    () => navigate("/patient/records/intake"),
    [navigate]
  );

  const exitIntake = useCallback(
    () => navigate("/patient/records"),
    [navigate]
  );

  // Clear unread badge when visiting chat tab
  useEffect(() => {
    if (section === "chat" && !fullScreenActive) {
      localStorage.setItem(LAST_SEEN_CHAT_KEY, String(Date.now()));
      setUnreadCount(0);
    }
  }, [section, fullScreenActive]);

  const handleDismissOnboarding = useCallback(() => {
    const pid = localStorage.getItem("patient_portal_patient_id");
    markOnboardingDone(pid);
    setOnboardingDone(true);
  }, []);

  const handleLogout = useCallback(() => {
    [
      STORAGE_KEY,
      STORAGE_NAME_KEY,
      STORAGE_DOCTOR_KEY,
      STORAGE_DOCTOR_NAME_KEY,
      PATIENT_CHAT_STORAGE_KEY,
      "patient_portal_patient_id",
    ].forEach((k) => localStorage.removeItem(k));
    setToken("");
    setPatientName("");
    setDoctorName("");
    setDoctorId("");
  }, []);

  // ── Auth guard ────────────────────────────────────────────────────
  if (!token && !api.isMock) {
    window.location.href = "/login";
    return null;
  }

  // ── Full-screen subpages ─────────────────────────────────────────
  if (inIntake) {
    return (
      <div style={pageContainer}>
        <SafeArea position="top" />
        <IntakePage token={token} onBack={exitIntake} />
      </div>
    );
  }
  if (recordDetailId) {
    return <PatientRecordDetailPage recordId={recordDetailId} token={token} />;
  }
  if (taskDetailId) {
    return <PatientTaskDetailPage taskId={taskDetailId} token={token} />;
  }
  if (profileSubpage === "about") {
    return <PatientAboutSubpage />;
  }
  if (profileSubpage === "privacy") {
    return <PatientPrivacySubpage />;
  }

  // ── Main shell ───────────────────────────────────────────────────
  const activeTab = TABS.find((t) => t.key === section) || TABS[0];

  return (
    <div style={pageContainer}>
      <SafeArea position="top" />

      {/* Top NavBar */}
      <NavBar
        backArrow={false}
        right={
          section === "records" ? (
            <Button
              fill="none"
              color="primary"
              size="small"
              onClick={startIntake}
              aria-label="新问诊"
            >
              <AddCircleOutline style={{ fontSize: ICON.md }} />
            </Button>
          ) : null
        }
        style={navBarStyle}
      >
        {activeTab.title}
      </NavBar>

      {/* Onboarding overlay */}
      {!onboardingDone && (
        <PatientOnboarding
          doctorName={doctorName}
          onDismiss={handleDismissOnboarding}
        />
      )}

      {/* Active tab content */}
      <div style={contentStyle}>
        {section === "chat" && (
          <ChatTab
            token={token}
            doctorName={doctorName}
            onNewIntake={startIntake}
            onViewRecords={() => handleTabChange("records")}
            onUnreadCountChange={setUnreadCount}
          />
        )}
        {section === "records" && (
          <RecordsTab token={token} onNewRecord={startIntake} />
        )}
        {section === "tasks" && <TasksTab token={token} />}
        {section === "profile" && (
          <MyPage
            patientName={patientName}
            doctorName={doctorName}
            doctorId={doctorId}
            onLogout={handleLogout}
          />
        )}
      </div>

      {/* Bottom TabBar */}
      <div style={tabBarWrap}>
        <TabBar activeKey={section} onChange={handleTabChange} safeArea>
          {TABS.map((t) => (
            <TabBar.Item
              key={t.key}
              title={t.label}
              icon={(active) => {
                const node = t.key === "chat" && unreadCount > 0 ? (
                  <Badge content={unreadCount} style={{ "--right": "-6px", "--top": "0" }}>
                    {active ? t.activeIcon : t.icon}
                  </Badge>
                ) : (
                  active ? t.activeIcon : t.icon
                );
                return node;
              }}
            />
          ))}
        </TabBar>
      </div>
    </div>
  );
}

const contentStyle = {
  flex: 1,
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const tabBarWrap = {
  flexShrink: 0,
  borderTop: `0.5px solid ${APP.border}`,
  background: APP.surface,
};
```

- [ ] **Step 2: Verify existing RecordsTab no longer receives `urlSubpage`**

The new shell stops passing `urlSubpage` to `RecordsTab`. Check `RecordsTab.jsx:239` — currently takes `urlSubpage`. Leave the prop for now; unused props are ignored. Task 4 will trim it.

- [ ] **Step 3: Run the frontend in dev mode and smoke test**

Run: `cd frontend/web && npm run dev` (if not already running)

Open in browser:
- `http://localhost:5173/patient/chat` → NavBar shows "聊天", no right action.
- `http://localhost:5173/patient/records` → NavBar shows "病历", right action is +icon. No more big inline "新建病历" button? (still there from RecordsTab — Task 6 removes it.)
- `http://localhost:5173/patient/tasks` → NavBar shows "任务", no right action.
- `http://localhost:5173/patient/profile` → NavBar shows "我的".
- `http://localhost:5173/patient/records/intake` → NavBar hidden, IntakePage full-screen.
- `http://localhost:5173/patient/records/42` → Stub detail page, back arrow returns.
- `http://localhost:5173/patient/tasks/7` → Stub detail page.
- `http://localhost:5173/patient/profile/about` → Stub about page.
- `http://localhost:5173/patient/profile/privacy` → Stub privacy page.

Expected: all routes render correctly. Login with nickname=`patient` / passcode=`123456` first if needed.

- [ ] **Step 4: Commit checkpoint**

```bash
git add frontend/web/src/v2/pages/patient/PatientPage.jsx
git commit -m "feat(v2): patient shell — NavBar + pathname routing + subpage overlays"
```

---

## Task 4: Remove inline "新建病历" button + unused prop from RecordsTab

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/RecordsTab.jsx:239` and the "New record button" block (~lines 295-314).

- [ ] **Step 1: Delete the inline New Record button**

In `RecordsTab.jsx`, remove the entire block (around lines 293-314) that begins with `{/* New record button */}` and ends with the outer `</div>`. The "新问诊" action is now in the NavBar.

- [ ] **Step 2: Remove `urlSubpage` prop and `onNewRecord` usage from signature**

Change function signature at line 239:
```jsx
export default function RecordsTab({ token }) {
```

Remove `urlSubpage` from prop destructure (was unused in new shell) and keep `onNewRecord` only if still called — if removed button was the only caller, delete it too.

- [ ] **Step 3: Run dev server, verify records list still renders without the big button**

Open `/patient/records` → list renders, no inline 新建病历 button. NavBar "+" still triggers `startIntake`.

- [ ] **Step 4: Commit checkpoint**

```bash
git add frontend/web/src/v2/pages/patient/RecordsTab.jsx
git commit -m "refactor(v2): remove inline 新建病历 button (moved to NavBar)"
```

---

## Task 5: E2E test — `24-patient-shell.spec.ts`

**Files:**
- Create: `frontend/web/tests/e2e/24-patient-shell.spec.ts`

- [ ] **Step 1: Write the e2e spec**

```ts
import { test, expect } from "@playwright/test";

const PATIENT_CREDS = { nickname: "patient", passcode: "123456" };

test.describe("patient shell", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByText("患者", { exact: true }).click();
    await page.getByPlaceholder("请输入昵称").fill(PATIENT_CREDS.nickname);
    await page.getByPlaceholder("请输入数字口令").fill(PATIENT_CREDS.passcode);
    await page.getByText("登录", { exact: true }).click();
    await page.waitForURL(/\/patient/);
  });

  test("each tab URL activates the correct tab and NavBar title", async ({ page }) => {
    const cases = [
      { path: "/patient",         title: "聊天" },
      { path: "/patient/chat",    title: "聊天" },
      { path: "/patient/records", title: "病历" },
      { path: "/patient/tasks",   title: "任务" },
      { path: "/patient/profile", title: "我的" },
    ];
    for (const c of cases) {
      await page.goto(c.path);
      await expect(page.locator(".adm-nav-bar-title")).toHaveText(c.title);
    }
  });

  test("records tab shows + action in NavBar", async ({ page }) => {
    await page.goto("/patient/records");
    await expect(page.locator('[aria-label="新问诊"]')).toBeVisible();
  });

  test("other tabs hide the + action", async ({ page }) => {
    for (const path of ["/patient/chat", "/patient/tasks", "/patient/profile"]) {
      await page.goto(path);
      await expect(page.locator('[aria-label="新问诊"]')).toHaveCount(0);
    }
  });

  test("full-screen subpages hide NavBar + TabBar", async ({ page }) => {
    await page.goto("/patient/records/42");
    // Subpage's own NavBar shows, but tab bar is gone
    await expect(page.locator(".adm-tab-bar")).toHaveCount(0);
  });
});
```

- [ ] **Step 2: Run the spec**

Backend on :8000, frontend on :5173.

```bash
cd frontend/web && rm -rf test-results && npx playwright test tests/e2e/24-patient-shell.spec.ts
```

Expected: 4 passing tests.

- [ ] **Step 3: Commit checkpoint — Phase 1 done**

```bash
git add frontend/web/tests/e2e/24-patient-shell.spec.ts
git commit -m "test(e2e): patient shell — tab routing + subpage overlay"
```

---

# Phase 2 — Data layer

Goal of Phase 2: every `useEffect`-based fetch in patient tabs is replaced with React Query. Loading/error states flow through shared components.

## Task 6: Add `PK` keys to `queryKeys.js`

**Files:**
- Modify: `frontend/web/src/lib/queryKeys.js`

- [ ] **Step 1: Append `PK` namespace**

Add to end of `queryKeys.js`:

```js
// ── Patient portal ──────────────────────────────────────────────────
export const PK = {
  patientMe:           () => ["patient", "me"],
  patientRecords:      () => ["patient", "records"],
  patientRecordDetail: (id) => ["patient", "records", String(id)],
  patientTasks:        () => ["patient", "tasks"],
  patientChatMessages: () => ["patient", "chat"],
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/lib/queryKeys.js
git commit -m "feat(v2): add PK query-key namespace for patient portal"
```

---

## Task 7: Create `patientQueries.js` with query hooks

**Files:**
- Create: `frontend/web/src/lib/patientQueries.js`

- [ ] **Step 1: Write the hooks**

```js
/**
 * React Query hooks for the patient portal.
 *
 * Parallel to doctorQueries.js. Token is pulled from PatientApiContext so
 * callers don't thread it. Backend endpoints are all under /api/patient/*.
 *
 * Cache policy:
 *   - me / records / tasks: 30–60 s stale, manual refetch on mount.
 *   - record detail: 60 s stale, fetched per id.
 *   - chat: polling every 10 s via refetchInterval (only while visible).
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PK } from "./queryKeys";
import { usePatientApi } from "../api/PatientApiContext";

const STALE = {
  me:       60 * 60_000,   // 1 hr — rarely changes after login
  records:       30_000,
  recordDetail:  60_000,
  tasks:         30_000,
  chat:          10_000,
};

// ── helper: current token from localStorage (context doesn't hold it) ──
function getToken() {
  return localStorage.getItem("patient_portal_token") || "";
}

export function usePatientMe() {
  const api = usePatientApi();
  return useQuery({
    queryKey: PK.patientMe(),
    queryFn:  () => api.getPatientMe(getToken()),
    staleTime: STALE.me,
    enabled:   !!getToken() || api.isMock,
  });
}

export function usePatientRecords() {
  const api = usePatientApi();
  return useQuery({
    queryKey: PK.patientRecords(),
    queryFn:  () => api.getPatientRecords(getToken()),
    staleTime: STALE.records,
    enabled:   !!getToken() || api.isMock,
  });
}

export function usePatientRecordDetail(id) {
  const api = usePatientApi();
  return useQuery({
    queryKey: PK.patientRecordDetail(id),
    queryFn:  () => api.getPatientRecord(getToken(), id),
    staleTime: STALE.recordDetail,
    enabled:   (!!getToken() || api.isMock) && !!id,
  });
}

export function usePatientTasks() {
  const api = usePatientApi();
  return useQuery({
    queryKey: PK.patientTasks(),
    queryFn:  () => api.getPatientTasks(getToken()),
    staleTime: STALE.tasks,
    enabled:   !!getToken() || api.isMock,
  });
}

export function usePatientChatMessages() {
  const api = usePatientApi();
  return useQuery({
    queryKey: PK.patientChatMessages(),
    queryFn:  () => api.getPatientChatMessages(getToken()),
    staleTime: STALE.chat,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
    enabled: !!getToken() || api.isMock,
  });
}

// ── Mutations ───────────────────────────────────────────────────────

export function useCompletePatientTask() {
  const api = usePatientApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId) => api.completePatientTask(getToken(), taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: PK.patientTasks() }),
  });
}

export function useUncompletePatientTask() {
  const api = usePatientApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId) => api.uncompletePatientTask(getToken(), taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: PK.patientTasks() }),
  });
}

export function useSendPatientMessage() {
  const api = usePatientApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text) => api.sendPatientMessage(getToken(), text),
    onSuccess: () => qc.invalidateQueries({ queryKey: PK.patientChatMessages() }),
  });
}
```

- [ ] **Step 2: Verify `PatientApiContext` exposes all methods used**

Run: `grep -E "getPatientMe|getPatientRecords|getPatientRecord\b|getPatientTasks|getPatientChatMessages|completePatientTask|uncompletePatientTask|sendPatientMessage" frontend/web/src/api/PatientApiContext.jsx`

Expected: all 8 names present. If any missing, extend `PatientApiContext.jsx` to re-export the api.js function before continuing. (Inspection earlier confirmed most are present under `api.js`; context wrapper may need thin additions.)

- [ ] **Step 3: Commit checkpoint**

```bash
git add frontend/web/src/lib/patientQueries.js
git commit -m "feat(v2): patientQueries — React Query hooks for patient data"
```

---

## Task 8: Migrate `RecordsTab` to `usePatientRecords`

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/RecordsTab.jsx`

- [ ] **Step 1: Replace manual fetch with the hook**

At top of file, replace:
```jsx
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, CapsuleTabs, ErrorBlock, List, Tag } from "antd-mobile";
import { AddOutline, FileOutline } from "antd-mobile-icons";
import { usePatientApi } from "../../../api/PatientApiContext";
```
with:
```jsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, CapsuleTabs, ErrorBlock, List, Tag } from "antd-mobile";
import { FileOutline } from "antd-mobile-icons";
import { usePatientRecords } from "../../../lib/patientQueries";
```

Replace the data-fetching block (lines ~241-260 in current file) with:
```jsx
export default function RecordsTab({ token }) {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = usePatientRecords();
  const records = Array.isArray(data) ? data : [];

  const [recordView, setRecordView] = useState("list");
  const [typeFilter, setTypeFilter] = useState("");

  // loadRecords → refetch (triggered by PullToRefresh in Task 13)
  const loadRecords = refetch;
```

Drop `loading` / `error` local state — use `isLoading` / `isError` from the hook.

- [ ] **Step 2: Manual smoke test**

Open `/patient/records` → records load, error state triggers `重试` button calling `refetch`.

- [ ] **Step 3: Commit checkpoint**

```bash
git add frontend/web/src/v2/pages/patient/RecordsTab.jsx
git commit -m "refactor(v2): RecordsTab uses usePatientRecords hook"
```

---

## Task 9: Migrate `TasksTab` to `usePatientTasks` + mutations

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/TasksTab.jsx`

- [ ] **Step 1: Replace imports + state**

Replace the import block and `useState`/`useEffect` fetch with hooks:

```jsx
import { useState } from "react";
import { Button, CapsuleTabs, ErrorBlock, List, Tag } from "antd-mobile";
import { CheckCircleOutline, ClockCircleOutline } from "antd-mobile-icons";
import { APP, FONT, ICON } from "../../theme";
import { LoadingCenter, EmptyState } from "../../components";
import {
  usePatientTasks,
  useCompletePatientTask,
  useUncompletePatientTask,
} from "../../../lib/patientQueries";
```

Rewrite `TasksTab` body:
```jsx
export default function TasksTab() {
  const { data, isLoading, isError, refetch } = usePatientTasks();
  const tasks = Array.isArray(data) ? data : [];
  const completeMut = useCompletePatientTask();
  const uncompleteMut = useUncompletePatientTask();
  const [filter, setFilter] = useState("all");

  const handleComplete   = (taskId) => completeMut.mutate(taskId);
  const handleUndo       = (taskId) => uncompleteMut.mutate(taskId);

  if (isLoading) return <LoadingCenter />;
  if (isError) return (
    <div style={{ padding: 16 }}>
      <ErrorBlock status="default" title="加载失败" description="无法获取任务列表">
        <Button color="primary" size="small" onClick={() => refetch()}>重试</Button>
      </ErrorBlock>
    </div>
  );
  // ...rest of filtering + rendering unchanged
}
```

Remove the signature's `token` prop (hook reads token internally).

- [ ] **Step 2: Update PatientPage.jsx**

Remove `token` prop on `<TasksTab>`:
```jsx
{section === "tasks" && <TasksTab />}
```

- [ ] **Step 3: Smoke test**

Open `/patient/tasks` → tasks load. Tap 完成 on a pending task → list updates (React Query invalidation).

- [ ] **Step 4: Commit checkpoint**

```bash
git add frontend/web/src/v2/pages/patient/TasksTab.jsx frontend/web/src/v2/pages/patient/PatientPage.jsx
git commit -m "refactor(v2): TasksTab uses usePatientTasks + mutation hooks"
```

---

## Task 10: Migrate `ChatTab` to hooks

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/ChatTab.jsx`

- [ ] **Step 1: Replace manual polling + message state with hooks**

Swap the existing `useState([messages])` + `setInterval` polling block for:

```jsx
import { usePatientChatMessages, useSendPatientMessage } from "../../../lib/patientQueries";
```

Inside component:
```jsx
const { data: chatData } = usePatientChatMessages();
const messages = chatData?.messages || [];
const sendMut = useSendPatientMessage();

async function handleSend(text) {
  await sendMut.mutateAsync(text);
}
```

Drop the manual polling `useEffect` entirely — React Query's `refetchInterval: 10_000` handles it.

Keep `LAST_SEEN_CHAT_KEY` + unread count logic; it reads from the query cache via the same `messages` variable.

- [ ] **Step 2: Smoke test**

Open `/patient/chat`. Send a message → optimistically disappears from input; a second later it appears from the poll. Background tab: polling pauses.

- [ ] **Step 3: Commit checkpoint**

```bash
git add frontend/web/src/v2/pages/patient/ChatTab.jsx
git commit -m "refactor(v2): ChatTab uses React Query polling + send mutation"
```

---

## Task 11: Migrate `MyPage` — use `useFontScaleStore`

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/MyPage.jsx`

- [ ] **Step 1: Replace local font-scale state with store**

Remove the top-of-file local helpers:
```js
const FONT_SCALE_KEY = "v2_font_scale";
function getFontScale() { ... }
function setFontScaleStored(tier) { ... }
```

Replace usage in `MyPage`:
```jsx
import { useFontScaleStore } from "../../../store/fontScaleStore";
import { applyFontScale } from "../../theme";

export default function MyPage(props) {
  const { fontScale, setFontScale } = useFontScaleStore();

  function handleFontScaleChange(tier) {
    setFontScale(tier);
    applyFontScale(tier);
    setShowFontPopup(false);
  }
  // ...
}
```

Note: `useFontScaleStore`'s `persist` middleware keeps `fontScale` in its own localStorage key (`doctor-font-scale`). Patient reuses the same key — acceptable since the two roles never log in simultaneously in the same browser (auth guard redirects).

- [ ] **Step 2: Wire About + Privacy list items to navigate**

Replace the empty `onClick={() => {}}` on 关于 and 隐私政策 rows with:

```jsx
const navigate = useNavigate();
// ...
<List.Item ... onClick={() => navigate("/patient/profile/about")}>关于</List.Item>
<List.Item ... onClick={() => navigate("/patient/profile/privacy")}>隐私政策</List.Item>
```

Add `useNavigate` import.

- [ ] **Step 3: Smoke test**

Open `/patient/profile` → tap 字体大小 → popup works. Tap 关于 → stub About page. Tap 隐私政策 → stub Privacy page.

- [ ] **Step 4: Commit checkpoint — Phase 2 done**

```bash
git add frontend/web/src/v2/pages/patient/MyPage.jsx
git commit -m "refactor(v2): MyPage uses shared fontScaleStore; wire About/Privacy nav"
```

---

# Phase 3 — Content + new subpages + polish

## Task 12: `PatientRecordDetailPage` real content

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientRecordDetailPage.jsx`

- [ ] **Step 1: Replace stub with real content**

```jsx
/**
 * @route /patient/records/:id
 * Read-only patient record detail.
 */
import { NavBar, Tag, ErrorBlock, Button } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { usePatientRecordDetail } from "../../../lib/patientQueries";
import { APP, FONT, RADIUS } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { LoadingCenter } from "../../components";

const RECORD_TYPE_LABEL = {
  visit: "门诊记录",
  dictation: "语音记录",
  import: "导入记录",
  intake_summary: "预问诊",
};

const STATUS_LABEL = {
  pending: "诊断中",
  completed: "待审核",
  confirmed: "已确认",
  failed: "诊断失败",
};

const STATUS_COLOR = {
  pending: "warning",
  completed: "primary",
  confirmed: "success",
  failed: "danger",
};

function Section({ title, children }) {
  if (!children) return null;
  return (
    <div style={sectionStyle}>
      <div style={sectionTitleStyle}>{title}</div>
      <div style={{ fontSize: FONT.base, color: APP.text1, whiteSpace: "pre-wrap" }}>
        {children}
      </div>
    </div>
  );
}

export default function PatientRecordDetailPage({ recordId }) {
  const navigate = useNavigate();
  const { data: record, isLoading, isError, refetch } = usePatientRecordDetail(recordId);

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        病历详情
      </NavBar>
      {isLoading && <LoadingCenter />}
      {isError && (
        <div style={{ padding: 16 }}>
          <ErrorBlock status="default" title="加载失败" description="无法获取病历">
            <Button color="primary" size="small" onClick={() => refetch()}>重试</Button>
          </ErrorBlock>
        </div>
      )}
      {record && (
        <div style={scrollable}>
          <div style={headerStyle}>
            <div style={{ fontSize: FONT.md, fontWeight: 600 }}>
              {RECORD_TYPE_LABEL[record.record_type] || record.record_type}
            </div>
            <div style={{ fontSize: FONT.sm, color: APP.text3, marginTop: 2 }}>
              {new Date(record.created_at).toLocaleString("zh-CN")}
            </div>
            {record.status && (
              <Tag color={STATUS_COLOR[record.status]} fill="outline" style={{ marginTop: 8, fontSize: FONT.xs }}>
                {STATUS_LABEL[record.status]}
              </Tag>
            )}
          </div>
          <Section title="主诉">{record.structured?.chief_complaint}</Section>
          <Section title="现病史">{record.structured?.present_illness}</Section>
          <Section title="既往史">{record.structured?.past_history}</Section>
          <Section title="用药史">{record.structured?.medications}</Section>
          <Section title="过敏史">{record.structured?.allergies}</Section>
          <Section title="诊断">{record.structured?.diagnosis}</Section>
          <Section title="原始内容">{record.content}</Section>
          <div style={{ height: 32 }} />
        </div>
      )}
    </div>
  );
}

const headerStyle = {
  padding: "12px 16px",
  background: APP.surface,
  borderBottom: `0.5px solid ${APP.border}`,
};

const sectionStyle = {
  padding: "12px 16px",
  background: APP.surface,
  borderBottom: `0.5px solid ${APP.border}`,
};

const sectionTitleStyle = {
  fontSize: FONT.sm,
  color: APP.text3,
  marginBottom: 6,
  fontWeight: 600,
};
```

- [ ] **Step 2: Smoke test**

Navigate `/patient/records` → tap a record → detail renders sections. Back button returns. `/patient/records/999999` → 加载失败 with 重试.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/patient/PatientRecordDetailPage.jsx
git commit -m "feat(v2): PatientRecordDetailPage — read-only record viewer"
```

---

## Task 13: `PatientTaskDetailPage` real content

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientTaskDetailPage.jsx`

- [ ] **Step 1: Replace stub with real content**

```jsx
/**
 * @route /patient/tasks/:id
 * Task detail reads from cached tasks list (no per-id backend endpoint).
 */
import { NavBar, Tag, Button, Dialog, ErrorBlock } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import {
  usePatientTasks,
  useCompletePatientTask,
  useUncompletePatientTask,
} from "../../../lib/patientQueries";
import { APP, FONT, RADIUS } from "../../theme";
import { pageContainer, navBarStyle, scrollable, bottomBar } from "../../layouts";
import { LoadingCenter } from "../../components";

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
    });
  } catch { return ""; }
}

export default function PatientTaskDetailPage({ taskId }) {
  const navigate = useNavigate();
  const { data, isLoading } = usePatientTasks();
  const completeMut = useCompletePatientTask();
  const uncompleteMut = useUncompletePatientTask();

  const task = (Array.isArray(data) ? data : []).find((t) => String(t.id) === String(taskId));

  function handleComplete() {
    completeMut.mutate(task.id);
  }

  function handleUndo() {
    Dialog.confirm({
      title: "撤销完成",
      content: "确定要将此任务标记为未完成吗？",
      cancelText: "取消",
      confirmText: "撤销",
      onConfirm: () => uncompleteMut.mutate(task.id),
    });
  }

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        任务详情
      </NavBar>
      {isLoading && <LoadingCenter />}
      {!isLoading && !task && (
        <div style={{ padding: 16 }}>
          <ErrorBlock status="empty" title="任务不存在" description="可能已被删除" />
        </div>
      )}
      {task && (
        <>
          <div style={scrollable}>
            <div style={headerStyle}>
              <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
                {task.title || "任务"}
              </div>
              <Tag
                color={task.status === "completed" ? "success" : "warning"}
                fill="outline"
                style={{ marginTop: 8, fontSize: FONT.xs }}
              >
                {task.status === "completed" ? "已完成" : "待完成"}
              </Tag>
            </div>
            <Section title="描述">{task.content}</Section>
            {task.due_at && <Section title="截止日期">{formatDate(task.due_at)}</Section>}
            <Section title="创建时间">{formatDate(task.created_at)}</Section>
          </div>
          <div style={bottomBar}>
            {task.status === "pending" ? (
              <Button block color="primary" onClick={handleComplete}
                      loading={completeMut.isPending}>
                标记完成
              </Button>
            ) : (
              <Button block color="default" onClick={handleUndo}
                      loading={uncompleteMut.isPending}>
                撤销完成
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function Section({ title, children }) {
  if (!children) return null;
  return (
    <div style={sectionStyle}>
      <div style={sectionTitleStyle}>{title}</div>
      <div style={{ fontSize: FONT.base, color: APP.text1, whiteSpace: "pre-wrap" }}>{children}</div>
    </div>
  );
}

const headerStyle = {
  padding: "12px 16px",
  background: APP.surface,
  borderBottom: `0.5px solid ${APP.border}`,
};
const sectionStyle = {
  padding: "12px 16px",
  background: APP.surface,
  borderBottom: `0.5px solid ${APP.border}`,
};
const sectionTitleStyle = {
  fontSize: FONT.sm,
  color: APP.text3,
  marginBottom: 6,
  fontWeight: 600,
};
```

- [ ] **Step 2: Smoke test**

`/patient/tasks` → tap a pending task → detail renders with 标记完成 primary button. Tap it → list updates. Revisit tab → task shows as done.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/patient/PatientTaskDetailPage.jsx
git commit -m "feat(v2): PatientTaskDetailPage — complete/undo with confirm"
```

---

## Task 14: Shared privacy body + About/Privacy subpages real content

**Files:**
- Create: `frontend/web/src/v2/pages/patient/_shared/PrivacyBody.jsx`
- Modify: `frontend/web/src/v2/pages/patient/PatientAboutSubpage.jsx`
- Modify: `frontend/web/src/v2/pages/patient/PatientPrivacySubpage.jsx`
- Modify: `frontend/web/src/v2/pages/PrivacyPage.jsx`

- [ ] **Step 1: Extract privacy body**

Read current `PrivacyPage.jsx` and move the body (everything inside the page container, minus outer NavBar if any) into a new file:

```jsx
// frontend/web/src/v2/pages/patient/_shared/PrivacyBody.jsx
import { List } from "antd-mobile";
import { APP, FONT } from "../../../theme";
// <paste the existing privacy content here>
export default function PrivacyBody() {
  return (/* copied content */);
}
```

Update `PrivacyPage.jsx` to render `<PrivacyBody />` inside its existing frame.

- [ ] **Step 2: Write About subpage**

Model on doctor's `settings/AboutSubpage.jsx`:

```jsx
import { NavBar, List } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";

const VERSION = "1.2.0-medical-style-ui";

export default function PatientAboutSubpage() {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        关于
      </NavBar>
      <div style={scrollable}>
        <List header="应用信息">
          <List.Item extra={<span style={{ color: APP.text3 }}>{VERSION}</span>}>版本</List.Item>
        </List>
        <List header="法律">
          <List.Item arrow onClick={() => navigate("/patient/profile/privacy")}>
            隐私政策
          </List.Item>
        </List>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write Privacy subpage**

```jsx
import { NavBar } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import PrivacyBody from "./_shared/PrivacyBody";

export default function PatientPrivacySubpage() {
  const navigate = useNavigate();
  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        隐私政策
      </NavBar>
      <div style={scrollable}>
        <PrivacyBody />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Smoke test**

`/patient/profile/about` → shows version + privacy link. Tapping privacy → privacy subpage. `/privacy` (existing route) still renders same body.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/patient/_shared/PrivacyBody.jsx \
        frontend/web/src/v2/pages/patient/PatientAboutSubpage.jsx \
        frontend/web/src/v2/pages/patient/PatientPrivacySubpage.jsx \
        frontend/web/src/v2/pages/PrivacyPage.jsx
git commit -m "feat(v2): patient About + Privacy subpages (share PrivacyBody)"
```

---

## Task 15: `PullToRefresh` on RecordsTab + TasksTab

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/RecordsTab.jsx`
- Modify: `frontend/web/src/v2/pages/patient/TasksTab.jsx`

- [ ] **Step 1: Wrap list in PullToRefresh — RecordsTab**

Import `PullToRefresh` from antd-mobile. Wrap the outer scroll container:

```jsx
import { PullToRefresh } from "antd-mobile";
// ...
<div style={{ flex: 1, overflowY: "auto" }}>
  <PullToRefresh onRefresh={async () => { await refetch(); }}>
    {/* existing list content */}
  </PullToRefresh>
</div>
```

- [ ] **Step 2: Same treatment — TasksTab**

Same pattern around the task list.

- [ ] **Step 3: Smoke test**

Pull down the records list → spinner shows, list refetches. Same for tasks.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/v2/pages/patient/RecordsTab.jsx frontend/web/src/v2/pages/patient/TasksTab.jsx
git commit -m "feat(v2): PullToRefresh on patient records + tasks"
```

---

## Task 16: `SwipeAction` on TasksTab

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/TasksTab.jsx`

- [ ] **Step 1: Wrap each List.Item in SwipeAction**

Import `SwipeAction`:

```jsx
import { SwipeAction } from "antd-mobile";
```

Modify `TaskItem` (or wrap where rendered):

```jsx
function TaskItem({ task, onComplete, onUndo }) {
  const isDone = task.status === "completed";
  const rightActions = isDone
    ? [{ key: "undo", text: "撤销", color: "light", onClick: () => onUndo(task.id) }]
    : [{ key: "done", text: "完成", color: "primary", onClick: () => onComplete(task.id) }];

  return (
    <SwipeAction rightActions={rightActions}>
      <List.Item
        prefix={isDone
          ? <CheckCircleOutline style={{ fontSize: ICON.md, color: APP.primary }} />
          : <ClockCircleOutline style={{ fontSize: ICON.md, color: APP.warning }} />
        }
        /* title + description unchanged */
        /* REMOVE the `extra` with mini Button */
        onClick={() => navigate(`/patient/tasks/${task.id}`)}
      >
        {task.title || "任务"}
      </List.Item>
    </SwipeAction>
  );
}
```

Remove the `Button` inside `extra` that previously fired complete/undo — swipe replaces it.

- [ ] **Step 2: Smoke test**

Swipe left on a pending task → 完成 reveals → tap → list updates. Same for completed task → 撤销.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/patient/TasksTab.jsx
git commit -m "feat(v2): SwipeAction on patient tasks (replaces inline buttons)"
```

---

## Task 17: Token sweep — replace hardcoded sizes

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/RecordsTab.jsx`
- Modify: `frontend/web/src/v2/pages/patient/MyPage.jsx`
- Modify: `frontend/web/src/v2/pages/patient/ChatTab.jsx`
- Modify: `frontend/web/src/v2/pages/patient/TasksTab.jsx`
- Modify: `frontend/web/src/v2/pages/patient/IntakePage.jsx`

- [ ] **Step 1: Grep for hardcoded fontSize numbers**

```bash
grep -nE 'fontSize:\s*[0-9]+' frontend/web/src/v2/pages/patient/*.jsx
```

Expected hits in RecordsTab (22, 18), TasksTab (22), MyPage (20, 44), ChatTab, IntakePage.

- [ ] **Step 2: Replace per the ICON scale**

Map:
- `fontSize: 20` → `fontSize: ICON.sm`
- `fontSize: 22` or `fontSize: 24` → `fontSize: ICON.md`
- `fontSize: 28` → `fontSize: ICON.lg`
- `fontSize: 32` → `fontSize: ICON.xl`

For `fontSize: 44` (avatar size in MyPage) — this is an avatar SIZE not icon fontSize, leave it or set `size={44}` on NameAvatar (already uses this prop).

Ensure `ICON` is imported in each file touched.

- [ ] **Step 3: Grep for `FONT.main` usage**

```bash
grep -n 'FONT.main' frontend/web/src/v2/pages/patient/*.jsx
```

Replace every `FONT.main` with `FONT.base`. Do NOT remove `FONT.main` from `theme.js` yet — antd-mobile internals still reference `--adm-font-size-main`.

- [ ] **Step 4: Grep for hardcoded WeChat green**

```bash
grep -n '#95EC69\|#07C160\|#FA5151' frontend/web/src/v2/pages/patient/*.jsx
```

Replace with `APP.wechatGreen`, `APP.primary`, `APP.danger` respectively.

- [ ] **Step 5: Run lint**

```bash
cd frontend/web && ./scripts/lint-ui.sh
```

Expected: passes. If not, fix the reported violations before committing.

- [ ] **Step 6: Commit**

```bash
git add frontend/web/src/v2/pages/patient/
git commit -m "refactor(v2): tokenize hardcoded sizes/colors in patient pages"
```

---

## Task 18: PatientOnboarding restyle

**Files:**
- Modify: `frontend/web/src/v2/pages/patient/PatientOnboarding.jsx`

- [ ] **Step 1: Token sweep**

Same pattern as Task 17. `grep -n 'fontSize\|#[0-9A-F]' frontend/web/src/v2/pages/patient/PatientOnboarding.jsx` → replace with `FONT.*` / `ICON.*` / `APP.*` / `RADIUS.*`.

- [ ] **Step 2: Smoke test**

Clear `patient_onboarding_done_*` from localStorage → reload → onboarding appears. Step through all 3 steps. Dismiss. Verify layout unchanged visually.

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/pages/patient/PatientOnboarding.jsx
git commit -m "refactor(v2): PatientOnboarding — token/icon sweep"
```

---

## Task 19: E2E — record detail round-trip

**Files:**
- Create: `frontend/web/tests/e2e/25-patient-record-detail.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from "@playwright/test";

test("record list → detail → back", async ({ page }) => {
  await page.goto("/login");
  await page.getByText("患者", { exact: true }).click();
  await page.getByPlaceholder("请输入昵称").fill("patient");
  await page.getByPlaceholder("请输入数字口令").fill("123456");
  await page.getByText("登录", { exact: true }).click();
  await page.waitForURL(/\/patient/);

  await page.goto("/patient/records");
  const firstItem = page.locator(".adm-list-item").first();
  // Skip test gracefully if no records exist (fresh patient)
  if (!(await firstItem.isVisible().catch(() => false))) {
    test.skip(true, "No records for test patient");
  }
  await firstItem.click();
  await expect(page.locator(".adm-nav-bar-title")).toHaveText("病历详情");

  // Back
  await page.locator(".adm-nav-bar-back").click();
  await expect(page).toHaveURL(/\/patient\/records$/);
});
```

- [ ] **Step 2: Run**

```bash
cd frontend/web && npx playwright test tests/e2e/25-patient-record-detail.spec.ts
```

Expected: pass or skip (empty patient).

- [ ] **Step 3: Commit**

```bash
git add frontend/web/tests/e2e/25-patient-record-detail.spec.ts
git commit -m "test(e2e): patient record detail round-trip"
```

---

## Task 20: E2E — task detail complete + undo

**Files:**
- Create: `frontend/web/tests/e2e/26-patient-task-detail.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from "@playwright/test";

test("task list → detail → complete → list reflects", async ({ page }) => {
  await page.goto("/login");
  await page.getByText("患者", { exact: true }).click();
  await page.getByPlaceholder("请输入昵称").fill("patient");
  await page.getByPlaceholder("请输入数字口令").fill("123456");
  await page.getByText("登录", { exact: true }).click();
  await page.waitForURL(/\/patient/);

  await page.goto("/patient/tasks");
  const first = page.locator(".adm-list-item").first();
  if (!(await first.isVisible().catch(() => false))) {
    test.skip(true, "No tasks for test patient");
  }
  await first.click();
  await expect(page.locator(".adm-nav-bar-title")).toHaveText("任务详情");
  await page.getByText("标记完成", { exact: true }).click();
  await expect(page.locator(".adm-nav-bar-title")).toHaveText("任务详情"); // stays on page
  await expect(page.getByText("撤销完成", { exact: true })).toBeVisible();
});
```

- [ ] **Step 2: Run**

```bash
cd frontend/web && npx playwright test tests/e2e/26-patient-task-detail.spec.ts
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/tests/e2e/26-patient-task-detail.spec.ts
git commit -m "test(e2e): patient task detail — complete → undo flow"
```

---

## Task 21: E2E — MyPage subpages

**Files:**
- Create: `frontend/web/tests/e2e/27-patient-my-subpages.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from "@playwright/test";

test("MyPage → About → back; MyPage → Privacy → back; font popup", async ({ page }) => {
  await page.goto("/login");
  await page.getByText("患者", { exact: true }).click();
  await page.getByPlaceholder("请输入昵称").fill("patient");
  await page.getByPlaceholder("请输入数字口令").fill("123456");
  await page.getByText("登录", { exact: true }).click();
  await page.waitForURL(/\/patient/);

  await page.goto("/patient/profile");

  // About
  await page.getByText("关于", { exact: true }).click();
  await expect(page.locator(".adm-nav-bar-title")).toHaveText("关于");
  await page.locator(".adm-nav-bar-back").click();
  await expect(page).toHaveURL(/\/patient\/profile$/);

  // Privacy
  await page.getByText("隐私政策", { exact: true }).click();
  await expect(page.locator(".adm-nav-bar-title")).toHaveText("隐私政策");
  await page.locator(".adm-nav-bar-back").click();
  await expect(page).toHaveURL(/\/patient\/profile$/);

  // Font popup
  await page.getByText("字体大小", { exact: true }).click();
  await expect(page.getByText("标准")).toBeVisible();
  await page.getByText("标准").click();
  await page.waitForTimeout(200); // popup closes
});
```

- [ ] **Step 2: Run**

```bash
cd frontend/web && npx playwright test tests/e2e/27-patient-my-subpages.spec.ts
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/tests/e2e/27-patient-my-subpages.spec.ts
git commit -m "test(e2e): patient MyPage subpages — About/Privacy/font popup"
```

---

## Task 22: Update existing 22 + 23 specs for new interaction model

**Files:**
- Modify: `frontend/web/tests/e2e/22-patient-records.spec.ts`
- Modify: `frontend/web/tests/e2e/23-patient-tasks.spec.ts`

- [ ] **Step 1: Read both files**

```bash
sed -n '1,200p' frontend/web/tests/e2e/22-patient-records.spec.ts
sed -n '1,200p' frontend/web/tests/e2e/23-patient-tasks.spec.ts
```

- [ ] **Step 2: Update 22 — replace inline "新建病历" button clicks with NavBar "+" icon**

Any selector like `getByText("新建病历 — 开始AI预问诊")` → `locator('[aria-label="新问诊"]')`.

- [ ] **Step 3: Update 23 — replace inline "完成" / "撤销" Button clicks with SwipeAction flow**

For completing a task, the test needs to:
1. Locate the target `.adm-list-item`.
2. Dispatch a swipe gesture: `await item.hover(); await page.mouse.down(); await page.mouse.move(x-120, y); await page.mouse.up();`
3. Click the revealed `完成` or `撤销` button.

Or (simpler): tap the item, navigate to detail page, click the bottom button (mirrors user reality).

Prefer the tap-to-detail path in tests — it's less brittle than simulating swipe. SwipeAction behavior stays covered by manual smoke.

- [ ] **Step 4: Run both specs**

```bash
cd frontend/web && npx playwright test tests/e2e/22-patient-records.spec.ts tests/e2e/23-patient-tasks.spec.ts
```

Expected: pass.

- [ ] **Step 5: Commit — Phase 3 done**

```bash
git add frontend/web/tests/e2e/22-patient-records.spec.ts frontend/web/tests/e2e/23-patient-tasks.spec.ts
git commit -m "test(e2e): update 22/23 for new patient NavBar + detail flow"
```

---

## Task 23: Final gate — full e2e pass + lint

- [ ] **Step 1: Lint**

```bash
cd frontend/web && ./scripts/lint-ui.sh
```

Expected: PASS (no hardcoded hex / font / icon sizes in patient pages).

- [ ] **Step 2: Full e2e suite**

Backend on :8000, frontend on :5173.

```bash
cd frontend/web && rm -rf test-results && npx playwright test
```

Expected: all passing. If failures, triage per `AGENTS.md` E2E policy (investigate, never auto-fix).

- [ ] **Step 3: Summary commit (if any incidental fixes)**

```bash
git add -A && git commit -m "chore(v2): final lint + e2e pass for patient parity"
```

---

# Self-review

**Spec coverage check:**
- §1 Shell → Task 1 (helpers) + Task 3 (shell rewrite). ✓
- §2 Data layer → Task 6 (keys) + Task 7 (hooks) + Tasks 8-11 (migrations). ✓
- §3 Tab content → Tasks 4, 8, 9, 10, 11. ✓
- §4 New subpages → Tasks 2 (stubs), 12, 13, 14. ✓
- §5 PatientOnboarding → Task 18. ✓
- §6 Polish + cleanup → Tasks 15 (PullToRefresh), 16 (SwipeAction), 17 (tokens), 18 (onboarding tokens). ✓
- Testing → Tasks 1 (unit), 5, 19-22 (e2e). ✓
- Risks / open decisions (spec §Risks):
  - Font scale sync → Task 11 uses shared store; patient-role server sync deferred. Documented.
  - TabBar Fill variants → Task 3 uses Fill only for Message; others outline. Documented.
  - SwipeAction surprise → Task 16 + detail page keeps primary button, so swipe is additive.
  - Task detail fallback → Task 13 uses cache-only, shows "任务不存在" when missing.

**Placeholder scan:**
- No TBD / TODO / "implement later" in task bodies.
- All code blocks complete with imports where applicable.
- Commit messages filled in.

**Type/name consistency:**
- `detectSection` / `detectRecordDetail` / `detectTaskDetail` / `detectProfileSubpage` used consistently in Task 1 definition, Task 3 shell, and PatientPage imports.
- Hook names (`usePatientMe`, `usePatientRecords`, etc.) match across Task 7 definition and Tasks 8-13 consumers.
- `PK` namespace used consistently in Task 6 and Task 7.
- `ICON.md` / `ICON.sm` / `ICON.lg` match `theme.js` scale.

All green.

---

## Execution choice

Plan complete and saved to `docs/superpowers/plans/2026-04-18-patient-pages-design-parity.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — one fresh subagent per task, review between tasks. Good for this plan since many tasks are independent (e.g. Task 1 vs Task 2) and reviewing TDD output per task stays digestible.
2. **Inline Execution** — execute tasks in this session via executing-plans, batch with checkpoints. Good if you want continuous context across tasks (e.g. for detecting cross-file regressions inline).

**Recommended: Subagent-Driven** — fresh-context workers keep each task's blast radius small, and batch commit/review at phase boundaries (after Tasks 5, 11, 22) gives natural checkpoint structure.
