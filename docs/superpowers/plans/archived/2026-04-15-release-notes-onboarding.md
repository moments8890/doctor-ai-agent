# Release Notes & Onboarding Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "what's new" rich-card modal for returning users after each release, and move onboarding wizard completion tracking from localStorage to a durable DB column.

**Architecture:** Two subsystems sharing one tracking layer. (1) `finished_onboarding` boolean on the `doctors` table gates the onboarding wizard redirect. (2) `seen_releases` JSON array in `user_preferences` controls the "what's new" modal. localStorage caches the seen list for instant offline reads; backend preferences are the source of truth. The `useReleaseNotes` hook syncs from backend before checking, avoiding cross-device race conditions.

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic (backend), React + MUI v7 + Zustand + React Query (frontend)

**Spec:** `docs/superpowers/specs/2026-04-15-release-notes-onboarding-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/db/models/doctor.py` | Modify | Add `finished_onboarding` column to `Doctor` model |
| `alembic/versions/0004_add_finished_onboarding.py` | Create | Schema + data migration |
| `src/channels/web/doctor_dashboard/profile_handlers.py` | Modify | Expose + accept `finished_onboarding` (write-once) |
| `src/channels/web/doctor_dashboard/preferences_handlers.py` | Modify | Add `seen_releases` with set-union merge logic |
| `frontend/web/src/config/releases.js` | Create | Release content config (versions + feature cards) |
| `frontend/web/src/store/releaseStore.js` | Create | Seen-release helpers (localStorage + backend sync) |
| `frontend/web/src/hooks/useReleaseNotes.js` | Create | Hook: sync → check → trigger modal |
| `frontend/web/src/components/ReleaseNotesDialog.jsx` | Create | Rich-card modal UI |
| `frontend/web/src/pages/doctor/DoctorPage.jsx` | Modify | Wire onboarding gate + release notes hook |
| `frontend/web/src/pages/doctor/OnboardingWizard.jsx` | Modify | On complete: set `finished_onboarding`, mark all seen |
| `frontend/web/src/api.js` | Modify | Extend `updateDoctorProfile` to accept `finished_onboarding` |

---

## Task 1: Backend — `finished_onboarding` column + migration

**Files:**
- Modify: `src/db/models/doctor.py:54-75`
- Create: `alembic/versions/0004_add_finished_onboarding.py`

- [ ] **Step 1: Add column to Doctor model**

In `src/db/models/doctor.py`, add to the `Doctor` class after the `updated_at` field (line 67):

```python
finished_onboarding: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("0"))
```

Also add `Boolean` to the imports from `sqlalchemy` and `import sqlalchemy as sa` if not present.

- [ ] **Step 2: Create Alembic migration**

Run:
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -m alembic revision --autogenerate -m "add_finished_onboarding"
```

- [ ] **Step 3: Add data migration to set existing doctors as onboarded**

Edit the generated migration file. In the `upgrade()` function, after the `op.add_column` call, add:

```python
# All existing doctors are already active — don't force them through onboarding
op.execute("UPDATE doctors SET finished_onboarding = 1")
```

The `downgrade()` should have `op.drop_column("doctors", "finished_onboarding")`.

- [ ] **Step 4: Run migration**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -m alembic upgrade head
```

- [ ] **Step 5: Verify**

```bash
cd /Volumes/ORICO/Code/doctor-ai-agent && .venv/bin/python -c "
from db.engine import engine_sync
from sqlalchemy import text
with engine_sync.connect() as conn:
    row = conn.execute(text('SELECT finished_onboarding FROM doctors LIMIT 1')).fetchone()
    print('Column exists, value:', row[0] if row else 'no rows')
"
```

Expected: `Column exists, value: 1` (or `no rows` if DB is empty)

---

## Task 2: Backend — Profile API exposes + accepts `finished_onboarding`

**Files:**
- Modify: `src/channels/web/doctor_dashboard/profile_handlers.py`

- [ ] **Step 1: Add `finished_onboarding` to GET response**

In `get_doctor_profile` (line 51-58), add `finished_onboarding` to the return dict:

```python
    return {
        "doctor_id": resolved_id,
        "name": name,
        "specialty": specialty,
        "clinic_name": clinic_name,
        "bio": bio,
        "onboarded": onboarded,
        "finished_onboarding": bool(doctor.finished_onboarding),
    }
```

- [ ] **Step 2: Add `finished_onboarding` to PATCH model (write-once)**

Add to `DoctorProfileUpdate`:

```python
class DoctorProfileUpdate(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    clinic_name: Optional[str] = None
    bio: Optional[str] = None
    finished_onboarding: Optional[bool] = None
```

In `patch_doctor_profile`, after the existing field-setting block (after line 86), add:

```python
    # Write-once: only allow false→true, never true→false
    if body.finished_onboarding is True:
        doctor.finished_onboarding = True
```

- [ ] **Step 3: Add `finished_onboarding` to PATCH response**

Update the return value of `patch_doctor_profile` (line 90):

```python
    return {
        "ok": True,
        "name": doctor.name or "",
        "specialty": doctor.specialty or "",
        "clinic_name": getattr(doctor, "clinic_name", "") or "",
        "bio": getattr(doctor, "bio", "") or "",
        "finished_onboarding": bool(doctor.finished_onboarding),
    }
```

- [ ] **Step 4: Verify with curl**

```bash
# GET — should include finished_onboarding
curl -s "http://localhost:8000/api/manage/profile?doctor_id=test_doctor" | python3 -m json.tool

# PATCH — set finished_onboarding
curl -s -X PATCH "http://localhost:8000/api/manage/profile?doctor_id=test_doctor" \
  -H "Content-Type: application/json" \
  -d '{"finished_onboarding": true}' | python3 -m json.tool
```

---

## Task 3: Backend — Preferences `seen_releases` with set-union merge

**Files:**
- Modify: `src/channels/web/doctor_dashboard/preferences_handlers.py`

- [ ] **Step 1: Add `seen_releases` to PreferencesUpdate model**

```python
class PreferencesUpdate(BaseModel):
    font_scale: Optional[str] = None
    seen_releases: Optional[list[str]] = None
```

- [ ] **Step 2: Add set-union merge logic in `patch_preferences`**

Replace the `updates = body.model_dump(exclude_none=True)` / `prefs.update(updates)` block (lines 66-67) with:

```python
    updates = body.model_dump(exclude_none=True)

    # List-type keys use set-union merge (don't overwrite)
    if "seen_releases" in updates:
        existing = set(prefs.get("seen_releases", []))
        incoming = set(updates.pop("seen_releases"))
        prefs["seen_releases"] = sorted(existing | incoming)

    # Scalar keys overwrite as before
    prefs.update(updates)
```

- [ ] **Step 3: Verify with curl**

```bash
# First write
curl -s -X PATCH "http://localhost:8000/api/manage/preferences?doctor_id=test_doctor" \
  -H "Content-Type: application/json" \
  -d '{"seen_releases": ["1.0.0"]}' | python3 -m json.tool

# Second write — should union, not replace
curl -s -X PATCH "http://localhost:8000/api/manage/preferences?doctor_id=test_doctor" \
  -H "Content-Type: application/json" \
  -d '{"seen_releases": ["2.0.0"]}' | python3 -m json.tool
# Expected: seen_releases: ["1.0.0", "2.0.0"]

# GET — verify
curl -s "http://localhost:8000/api/manage/preferences?doctor_id=test_doctor" | python3 -m json.tool
```

---

## Task 4: Frontend — Release config file

**Files:**
- Create: `frontend/web/src/config/releases.js`

- [ ] **Step 1: Create the release config**

```js
// frontend/web/src/config/releases.js
//
// Release notes content. Newest release first.
// On each release, prepend a new entry with the version, date, title,
// and feature cards. Icons are direct MUI component imports.

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import GroupsIcon from "@mui/icons-material/Groups";
import AssignmentTurnedInIcon from "@mui/icons-material/AssignmentTurnedIn";

export const RELEASES = [
  {
    version: "2.0.0",
    date: "2026-04-15",
    title: "v2.0 更新内容",
    features: [
      {
        icon: AutoAwesomeIcon,
        title: "AI 智能随访",
        description: "基于您的知识库，自动生成个性化随访建议",
      },
      {
        icon: MenuBookIcon,
        title: "知识库升级",
        description: "支持网页导入、拍照上传，AI 自动提取要点",
      },
      {
        icon: GroupsIcon,
        title: "患者管理",
        description: "查看患者问诊记录，跟踪随访进度",
      },
      {
        icon: AssignmentTurnedInIcon,
        title: "审核工作台",
        description: "一站式审核 AI 生成的诊断建议和回复草稿",
      },
    ],
  },
];

export function getLatestRelease() {
  return RELEASES[0] || null;
}
```

---

## Task 5: Frontend — Seen-release store helpers

**Files:**
- Create: `frontend/web/src/store/releaseStore.js`

- [ ] **Step 1: Create the store module**

```js
// frontend/web/src/store/releaseStore.js
//
// Seen-release tracking: localStorage (fast read) + backend preferences (durable).
// Mirrors the pattern in onboardingWizardState.js.

import { getPreferences, updatePreferences } from "../api";
import { RELEASES } from "../config/releases";

const LS_KEY = "seen_releases";

function lsKey(doctorId) {
  return `${LS_KEY}:${doctorId}`;
}

/** Read seen versions from localStorage (fast, offline). */
export function getSeenReleases(doctorId) {
  try {
    return JSON.parse(localStorage.getItem(lsKey(doctorId))) || [];
  } catch {
    return [];
  }
}

/** Check if the latest release version is unseen. */
export function hasUnseenRelease(doctorId, latestVersion) {
  return !getSeenReleases(doctorId).includes(latestVersion);
}

/** Write one version to localStorage + fire-and-forget to backend. */
export function markReleaseSeen(doctorId, version) {
  const seen = getSeenReleases(doctorId);
  if (!seen.includes(version)) {
    seen.push(version);
    localStorage.setItem(lsKey(doctorId), JSON.stringify(seen));
    updatePreferences(doctorId, { seen_releases: seen }).catch(() => {});
  }
}

/** Mark ALL existing releases as seen (called after onboarding completion). */
export function markAllReleasesSeen(doctorId) {
  const allVersions = RELEASES.map((r) => r.version);
  localStorage.setItem(lsKey(doctorId), JSON.stringify(allVersions));
  updatePreferences(doctorId, { seen_releases: allVersions }).catch(() => {});
}

/**
 * Sync from backend — MERGES local + remote (never overwrites).
 * Call after login. Returns a promise so callers can await completion.
 */
export async function syncSeenReleases(doctorId) {
  try {
    const prefs = await getPreferences(doctorId);
    const remote = prefs?.seen_releases || [];
    const local = getSeenReleases(doctorId);
    const merged = [...new Set([...local, ...remote])];
    localStorage.setItem(lsKey(doctorId), JSON.stringify(merged));
    // Write merged back if local had entries the backend missed
    if (merged.length > remote.length) {
      updatePreferences(doctorId, { seen_releases: merged }).catch(() => {});
    }
  } catch {
    // Network error — localStorage value stands
  }
}
```

---

## Task 6: Frontend — `useReleaseNotes` hook

**Files:**
- Create: `frontend/web/src/hooks/useReleaseNotes.js`

- [ ] **Step 1: Create the hook**

```js
// frontend/web/src/hooks/useReleaseNotes.js
//
// Triggers the "what's new" modal for returning users.
// Waits for backend sync before checking (prevents cross-device race).

import { useState, useEffect, useCallback } from "react";
import { getLatestRelease } from "../config/releases";
import {
  syncSeenReleases,
  hasUnseenRelease,
  markReleaseSeen,
} from "../store/releaseStore";

export function useReleaseNotes(doctorId, finishedOnboarding) {
  const [showDialog, setShowDialog] = useState(false);
  const [release, setRelease] = useState(null);
  const [syncDone, setSyncDone] = useState(false);

  // Step 1: sync seen_releases from backend (merges local + remote)
  useEffect(() => {
    if (!doctorId || !finishedOnboarding) return;
    syncSeenReleases(doctorId).finally(() => setSyncDone(true));
  }, [doctorId, finishedOnboarding]);

  // Step 2: after sync completes, check for unseen releases
  useEffect(() => {
    if (!syncDone || !doctorId) return;
    const latest = getLatestRelease();
    if (!latest) return;
    if (!hasUnseenRelease(doctorId, latest.version)) return;

    // Short delay so the page paints first
    const timer = setTimeout(() => {
      setRelease(latest);
      setShowDialog(true);
    }, 300);
    return () => clearTimeout(timer);
  }, [syncDone, doctorId]);

  const dismiss = useCallback(() => {
    setShowDialog(false);
    if (release) markReleaseSeen(doctorId, release.version);
  }, [doctorId, release]);

  return { showDialog, release, dismiss };
}
```

---

## Task 7: Frontend — `ReleaseNotesDialog` component

**Files:**
- Create: `frontend/web/src/components/ReleaseNotesDialog.jsx`

- [ ] **Step 1: Create the dialog component**

```jsx
// frontend/web/src/components/ReleaseNotesDialog.jsx
//
// "What's new" rich-card modal. Uses SheetDialog (bottom sheet on mobile).

import { Box, Typography } from "@mui/material";
import SheetDialog from "./SheetDialog";
import DialogFooter from "./DialogFooter";
import { TYPE, COLOR, RADIUS } from "../theme";

function FeatureCard({ icon: Icon, title, description }) {
  return (
    <Box
      sx={{
        display: "flex",
        gap: 1.5,
        p: 1.5,
        bgcolor: COLOR.surfaceAlt,
        borderRadius: RADIUS.md,
      }}
    >
      <Box
        sx={{
          width: 40,
          height: 40,
          borderRadius: RADIUS.sm,
          bgcolor: COLOR.primaryLight,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon sx={{ fontSize: 20, color: COLOR.primary }} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography sx={{ ...TYPE.heading, mb: 0.25 }}>{title}</Typography>
        <Typography sx={{ ...TYPE.secondary, color: COLOR.text3 }}>
          {description}
        </Typography>
      </Box>
    </Box>
  );
}

export default function ReleaseNotesDialog({ open, release, onDismiss }) {
  if (!release) return null;

  return (
    <SheetDialog
      open={open}
      onClose={onDismiss}
      title={release.title}
      footer={
        <DialogFooter
          showCancel={false}
          confirmLabel="知道了"
          onConfirm={onDismiss}
        />
      }
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, py: 1 }}>
        {release.features.map((f, i) => (
          <FeatureCard key={i} {...f} />
        ))}
      </Box>
    </SheetDialog>
  );
}
```

---

## Task 8: Frontend — Extend `updateDoctorProfile` in api.js

**Files:**
- Modify: `frontend/web/src/api.js:605-611`

- [ ] **Step 1: Extend `updateDoctorProfile` to forward all fields**

Replace the `updateDoctorProfile` function (lines 605-611):

```js
export async function updateDoctorProfile(doctorId, fields) {
  const qs = new URLSearchParams({ doctor_id: doctorId });
  return request(`/api/manage/profile?${qs.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}
```

This changes the signature from `(doctorId, { name, specialty })` to
`(doctorId, fields)` — passing the full object through. All existing callers
already pass `{ name, specialty }` as the second arg, so this is backward
compatible.

- [ ] **Step 2: Verify existing callers still work**

Search for all callers of `updateDoctorProfile`:
```bash
cd /Volumes/ORICO/Code/doctor-ai-agent/frontend/web && grep -rn "updateDoctorProfile" src/
```

Confirm they all pass an object as the second argument (they do — `DoctorPage.jsx` line 776 and `SettingsPage.jsx`).

---

## Task 9: Frontend — Wire onboarding gate + release notes into DoctorPage

**Files:**
- Modify: `frontend/web/src/pages/doctor/DoctorPage.jsx`

- [ ] **Step 1: Add imports**

At the top of `DoctorPage.jsx`, add:

```js
import { useReleaseNotes } from "../../hooks/useReleaseNotes";
import ReleaseNotesDialog from "../../components/ReleaseNotesDialog";
import { getDoctorProfile, updateDoctorProfile } from "../../api";
```

Note: `getDoctorProfile` and `updateDoctorProfile` are already available inside
`useDoctorPageState` via `useApi()`, but the onboarding gate runs in the main
`DoctorPage` component, so we import them directly from `api.js` here.

- [ ] **Step 2: Replace localStorage wizard check with profile-based gate**

In the `DoctorPage` component (around line 796-805), replace:

```js
  // Redirect to onboarding wizard on first login (skip for /mock and wizard subpages)
  useEffect(() => {
    if (!doctorId) return;
    if (window.location.pathname.startsWith("/mock")) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("wizard") === "1" || params.get("onboarding") === "1") return;
    if (!isWizardDone(doctorId)) {
      navigate(dp("onboarding"));
    }
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps
```

With:

```js
  // Onboarding gate: redirect if not onboarded (from profile API, not localStorage).
  // Also handles one-time migration: if localStorage says done but DB says not,
  // patch the profile (covers users who completed wizard before this feature).
  const [finishedOnboarding, setFinishedOnboarding] = useState(true); // default true to avoid flash
  useEffect(() => {
    if (!doctorId) return;
    if (window.location.pathname.startsWith("/mock")) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("wizard") === "1" || params.get("onboarding") === "1") return;

    getDoctorProfile(doctorId).then((p) => {
      if (p.finished_onboarding) {
        setFinishedOnboarding(true);
      } else if (isWizardDone(doctorId)) {
        // One-time migration: localStorage says done, DB doesn't know yet
        updateDoctorProfile(doctorId, { finished_onboarding: true }).catch(() => {});
        setFinishedOnboarding(true);
      } else {
        setFinishedOnboarding(false);
        navigate(dp("onboarding"));
      }
    }).catch(() => {});
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps
```

Also import `updateDoctorProfile` from `../../api` if not already imported.

- [ ] **Step 3: Add the release notes hook**

After the `finishedOnboarding` state block, add:

```js
  const { showDialog: showReleaseNotes, release: releaseData, dismiss: dismissReleaseNotes } = useReleaseNotes(doctorId, finishedOnboarding);
```

- [ ] **Step 4: Render the ReleaseNotesDialog**

In the return JSX, after the `<OnboardingDialog>` line (around line 854), add:

```jsx
      <ReleaseNotesDialog open={showReleaseNotes} release={releaseData} onDismiss={dismissReleaseNotes} />
```

---

## Task 10: Frontend — OnboardingWizard marks `finished_onboarding` + all releases seen

**Files:**
- Modify: `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

- [ ] **Step 1: Add imports**

Add at the top:

```js
import { updateDoctorProfile } from "../../api";
import { markAllReleasesSeen } from "../../store/releaseStore";
```

- [ ] **Step 2: Update `handleAdvance` (wizard completion)**

In the `handleAdvance` function (around line 531-543), after `markWizardDone(doctorId, "completed")`, add:

```js
      markWizardDone(doctorId, "completed");
      // Persist to backend + suppress all existing release notes
      updateDoctorProfile(doctorId, { finished_onboarding: true }).catch(() => {});
      markAllReleasesSeen(doctorId);
      navigate(dp());
```

- [ ] **Step 3: Update `handleSkip` (wizard skip)**

In the `handleSkip` function (around line 548-551), after `markWizardDone(doctorId, "skipped")`, add:

```js
  function handleSkip() {
    markWizardDone(doctorId, "skipped");
    updateDoctorProfile(doctorId, { finished_onboarding: true }).catch(() => {});
    markAllReleasesSeen(doctorId);
    navigate(dp());
  }
```

---

## Task 11: Manual QA verification

- [ ] **Step 1: Test new user flow**

1. Start backend on :8000 and frontend on :5173
2. Register a new doctor (use invite code WELCOME)
3. Verify: redirected to `/doctor/onboarding` wizard
4. Complete or skip the wizard
5. Verify: lands on MyAI page, NO "what's new" modal appears (all releases marked seen)

- [ ] **Step 2: Test returning user flow**

1. As the same doctor, add a new release entry to `releases.js` with version `"99.0.0"`
2. Reload the page
3. Verify: "what's new" modal appears after MyAI loads
4. Click "知道了"
5. Verify: modal dismissed, does not reappear on reload

- [ ] **Step 3: Test cross-device durability**

1. Open an incognito/private window (simulates new device)
2. Log in as the same doctor
3. Verify: the v99.0.0 modal does NOT appear (backend has it as seen)

- [ ] **Step 4: Remove the test release entry**

Remove the `"99.0.0"` entry from `releases.js`.

---

## Task 12: Add to wiki

**Files:**
- Modify: `frontend/web/public/wiki/wiki-home.html` (or appropriate wiki page)

- [ ] **Step 1: Add release notes section to wiki**

Add a section documenting how to add new release notes for future releases.
Content should cover:
- Where the config file is (`frontend/web/src/config/releases.js`)
- How to add a new release (prepend entry with version, date, title, features)
- How icons work (direct MUI imports)
- That new users who onboard after a release never see old release notes
