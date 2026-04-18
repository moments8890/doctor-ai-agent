# Feature Release Notes & Onboarding System

**Date:** 2026-04-15
**Status:** Reviewed (Claude + Codex co-review applied)

## Problem

No mechanism to show users what's new after a release, and the onboarding
wizard completion state lives only in localStorage (lost on device switch or
browser clear). We need:

1. A "what's new" modal for returning users on each release
2. Durable onboarding completion tracking in the database
3. Both managed by a unified "seen" tracking layer

## Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Onboarding vs release notes | Separate concerns | Different UX: wizard (interactive) vs modal (read & dismiss) |
| Release content storage | JS config file in frontend | Developer-authored, structured data, no backend needed |
| Seen-release tracking | localStorage (read) + backend preferences (write-through) | Fast offline checks + cross-device durability |
| Onboarding tracking | `finished_onboarding` column on `doctors` table | Stable boolean in DB, survives browser clears |
| Trigger point | After MyAI page loads (with delay) | Non-blocking; user sees their dashboard first |
| Modal style | Rich cards (icon + title + description) | Informative without being interactive/complex |

## Architecture

### User Flow

```
Login
  |
  v
finished_onboarding == false?  (from profile API)
  |                       |
  YES (false)             NO (true)
  |                       |
  v                       v
Redirect to              MyAI page loads
/doctor/onboarding         |
  |                       v
  v                  syncSeenReleases()
Wizard complete        (merge local + remote)
  |                       |
  v                       v
Set finished_onboarding  Check: latest release version
  = true                   in merged seen_releases?
+ mark ALL releases        |           |
  as seen                 YES          NO
  |                       |           |
  v                       v           v
Redirect to MyAI       Normal     Show "What's New"
                        experience   modal (300ms delay)
                                     |
                                     v
                                   User dismisses
                                     |
                                     v
                                   Write seen version to
                                   localStorage + backend
```

### Components

#### 1. Release Config File

**File:** `frontend/web/src/config/releases.js`

```js
export const RELEASES = [
  {
    version: "2.0.0",
    date: "2026-04-15",
    title: "全新发布",
    features: [
      {
        icon: AutoAwesomeIcon,     // Direct MUI import
        title: "AI 智能随访",
        description: "基于您的知识库，自动生成个性化随访建议",
      },
      {
        icon: MenuBookIcon,
        title: "知识库管理",
        description: "支持网页导入、拍照上传，AI 自动提取要点",
      },
      // ...more feature cards
    ],
  },
  // Future releases prepended here
];

export function getLatestRelease() {
  return RELEASES[0] || null;
}

export function getReleaseByVersion(version) {
  return RELEASES.find(r => r.version === version) || null;
}
```

Each release entry: version string, date, title, and array of feature cards.
Icons are direct MUI component imports (not string names) since the config is a
JS file, giving compile-time errors for typos.

#### 2. Backend: `finished_onboarding` Column

**Migration:** Add `finished_onboarding` Boolean column to `doctors` table.

```python
# Alembic migration — schema + data
op.add_column("doctors", sa.Column(
    "finished_onboarding", sa.Boolean(),
    nullable=False, server_default=sa.text("0"),
))

# Data migration: all existing doctors are treated as onboarded.
# Without this, doctors who cleared their browser or switched devices
# would be incorrectly forced through onboarding again.
op.execute("UPDATE doctors SET finished_onboarding = 1")
```

- Default `false` for **new** doctors (column default)
- **All existing** doctors set to `true` in the data migration (they're already
  active users — forcing them through onboarding would be wrong)
- The frontend localStorage check (`isWizardDone`) becomes a secondary fallback,
  not the primary migration path

**API changes:**

- `GET /api/manage/profile` — already returns doctor fields; will now include
  `finished_onboarding`
- `PATCH /api/manage/profile` — accept `finished_onboarding` field, but
  **write-once only** (false→true allowed, true→false rejected silently):

```python
# In profile PATCH handler:
if body.finished_onboarding is True:
    doctor.finished_onboarding = True
# Silently ignore finished_onboarding=false — never re-gate a doctor
```

No new endpoints needed.

**Naming note:** The existing profile response already has an `onboarded` field
(derived from `bool(name and name != id)` — meaning "has set their name"). The
new `finished_onboarding` means "completed the wizard." These are different
concepts and coexist:
- `onboarded` → has a profile name (controls name-setting dialog)
- `finished_onboarding` → completed wizard (controls onboarding redirect)

#### 3. Backend: `seen_releases` in Preferences

The existing `UserPreferences` model stores a JSON blob. Add `seen_releases` key:

```json
{
  "font_scale": "standard",
  "seen_releases": ["1.0.0", "2.0.0"]
}
```

**API changes to preferences handler:**

- `PreferencesUpdate` model: add `seen_releases: Optional[list[str]] = None`
- PATCH behavior: `seen_releases` requires **explicit set-union logic** in
  `patch_preferences`. The existing `prefs.update(updates)` would overwrite the
  list. Instead, special-case list-type keys before the generic update:

```python
# In patch_preferences, before prefs.update(updates):
if "seen_releases" in updates:
    existing = set(prefs.get("seen_releases", []))
    incoming = set(updates.pop("seen_releases"))
    prefs["seen_releases"] = sorted(existing | incoming)
prefs.update(updates)  # handles remaining scalar keys (font_scale, etc.)
```

This ensures cross-device writes never silently drop versions.

**Frontend API:**

```js
// Extend existing updatePreferences
updatePreferences(doctorId, { seen_releases: ["2.0.0"] })
// Backend unions with existing array, deduplicates
```

#### 4. Frontend: Seen-Release Store

**File:** `frontend/web/src/store/releaseStore.js`

Lightweight module (not a Zustand store — just helper functions) mirroring the
`onboardingWizardState.js` pattern:

```js
const LS_KEY = "seen_releases";

function lsKey(doctorId) { return `${LS_KEY}:${doctorId}`; }

// Read from localStorage (fast, offline)
export function getSeenReleases(doctorId) {
  try {
    return JSON.parse(localStorage.getItem(lsKey(doctorId))) || [];
  } catch { return []; }
}

// Write to localStorage + fire-and-forget to backend
export function markReleaseSeen(doctorId, version) {
  const seen = getSeenReleases(doctorId);
  if (!seen.includes(version)) {
    seen.push(version);
    localStorage.setItem(lsKey(doctorId), JSON.stringify(seen));
    updatePreferences(doctorId, { seen_releases: seen }).catch(() => {});
  }
}

// Sync from backend (call after login) — MERGES local + remote, never overwrites
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
  } catch { /* localStorage value stands */ }
}

export function hasUnseenRelease(doctorId, latestVersion) {
  return !getSeenReleases(doctorId).includes(latestVersion);
}

// Mark ALL existing releases as seen (used after onboarding completion)
export function markAllReleasesSeen(doctorId) {
  const allVersions = RELEASES.map(r => r.version);
  localStorage.setItem(lsKey(doctorId), JSON.stringify(allVersions));
  updatePreferences(doctorId, { seen_releases: allVersions }).catch(() => {});
}
```

#### 5. Frontend: ReleaseNotesDialog Component

**File:** `frontend/web/src/components/ReleaseNotesDialog.jsx`

Uses `SheetDialog` (existing bottom-sheet component) to display release cards.

**Structure:**
```
SheetDialog (title = release.title, e.g. "v2.0 更新内容")
  |
  +-- Scrollable card list
  |     +-- FeatureCard (icon + title + description)  x N
  |     +-- FeatureCard
  |     +-- ...
  |
  +-- Footer: single "知道了" button (primary green, full width)
```

**FeatureCard layout:**
```
+------+----------------------------+
| Icon |  Title (heading)           |
| (40) |  Description (secondary)   |
+------+----------------------------+
```

- Icon: `IconBadge` component (existing) with the MUI icon name
- Title: `TYPE.heading` weight 600
- Description: `TYPE.secondary` color `COLOR.text3`
- Card has light background (`COLOR.surfaceAlt`), `RADIUS.md` corners
- Gap between cards: 12px

**Icon resolution:** Icons are imported directly in `releases.js` and passed as
React components — no string-to-component lookup map needed. This gives
compile-time errors for bad icon names and avoids runtime resolution overhead.

#### 6. Frontend: Integration Point — useReleaseNotes Hook

**File:** `frontend/web/src/hooks/useReleaseNotes.js`

Custom hook used in `DoctorPage.jsx` (the main shell):

```js
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
    if (!syncDone) return;
    const latest = getLatestRelease();
    if (!latest) return;
    if (!hasUnseenRelease(doctorId, latest.version)) return;

    // Short delay so the page paints first
    const timer = setTimeout(() => {
      setRelease(latest);
      setShowDialog(true);
    }, 300);
    return () => clearTimeout(timer);
  }, [syncDone]);

  const dismiss = useCallback(() => {
    setShowDialog(false);
    if (release) markReleaseSeen(doctorId, release.version);
  }, [doctorId, release]);

  return { showDialog, release, dismiss };
}
```

Key behaviors:
- **Waits for sync** before checking — prevents showing already-dismissed modals
  on a new device (fixes cross-device race condition)
- Only triggers when `finishedOnboarding` is true (no double-prompt for new users)
- 300ms delay after sync so the page paints first
- `dismiss` writes to both localStorage and backend
- Runs once per mount — no re-triggering on tab switches
- If sync fails (network error), `finally()` still sets `syncDone=true` and
  falls back to localStorage (which may be empty on a new device — acceptable,
  showing the modal again is a minor annoyance, not data loss)

#### 7. Frontend: Onboarding Gate Enhancement

In `DoctorPage.jsx` or the auth-required wrapper:

```js
// After login, check finished_onboarding from profile API
const { data: profile } = useQuery({ queryKey: ["doctor-profile", doctorId], ... });

// Redirect if not onboarded
useEffect(() => {
  if (profile && !profile.finished_onboarding) {
    navigate("/doctor/onboarding");
  }
}, [profile]);
```

In `OnboardingWizard.jsx`, on completion:
```js
// Existing: markWizardDone(doctorId)  — localStorage
// New: PATCH /api/manage/profile { finished_onboarding: true }
// New: markAllReleasesSeen(doctorId)  — marks ALL existing versions as seen
```

**Why mark all, not just current?** A new doctor who registers during v3.0 has
never used v1.0 or v2.0. Showing them "what's new in v2.0" is meaningless — they
learned the current state through onboarding. They should only see release notes
for versions released *after* they completed onboarding.

**Migration for existing users:**
The Alembic data migration sets `finished_onboarding = true` for all existing
doctors (see section 2). This is the primary migration path — it covers all
existing doctors regardless of browser state.

As a secondary fallback, the frontend still checks: if `isWizardDone(doctorId)`
is true in localStorage but `profile.finished_onboarding` is false (e.g., doctor
registered between migration deploy and frontend deploy), PATCH the profile to
set `finished_onboarding = true`.

### Files Changed

| File | Change |
|------|--------|
| `src/db/models/doctor.py` | Add `finished_onboarding` column |
| `alembic/versions/XXXX_add_finished_onboarding.py` | Migration |
| `src/channels/web/doctor_dashboard/profile_handlers.py` | Expose + accept `finished_onboarding` |
| `src/channels/web/doctor_dashboard/preferences_handlers.py` | Add `seen_releases` to `PreferencesUpdate` model, merge-append logic |
| `frontend/web/src/config/releases.js` | **New** — release content config |
| `frontend/web/src/store/releaseStore.js` | **New** — seen-release helpers |
| `frontend/web/src/hooks/useReleaseNotes.js` | **New** — hook for trigger logic |
| `frontend/web/src/components/ReleaseNotesDialog.jsx` | **New** — modal UI |
| `frontend/web/src/pages/doctor/DoctorPage.jsx` | Add onboarding gate + release notes hook |
| `frontend/web/src/pages/doctor/OnboardingWizard.jsx` | On complete: set `finished_onboarding`, mark release seen |
| `frontend/web/src/api.js` | Add `updateProfile` if not present, extend `updatePreferences` |

### What This Does NOT Include

- Admin UI for editing release notes (author in code, not in UI)
- Patient-facing release notes (patients use a simple chat interface)
- Analytics on release note views (can add later via the `seen_releases` data)
- Push notifications for new releases (modal on next visit is sufficient)
- Versioned onboarding (one wizard flow; future changes are release notes)

### Testing Strategy

- **Unit:** `releaseStore.js` — mark seen, sync, dedup
- **Unit:** `useReleaseNotes` hook — shows when unseen, doesn't show when seen,
  doesn't show when `finishedOnboarding` is false
- **Backend:** preferences PATCH appends to `seen_releases` without duplicates
- **Backend:** migration adds column with correct default
- **E2E:** New user → onboarding wizard → complete → no "what's new" modal.
  Returning user with unseen release → modal appears → dismiss → doesn't reappear.
