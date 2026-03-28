# API Context + Mock Unification Design

**Status: ✅ COMPLETED (2026-03-27)**

**Date:** 2026-03-26
**Goal:** Eliminate duplicate mock pages by making MockPages render the real DoctorPage with fake API responses via a React context provider. Mock mode uses `/debug/doctor/*` URLs with full browser routing.

## Problem

MockPages.jsx (742 lines) maintains its own versions of every doctor page (MockHome, MockPatients, MockPatientDetail, MockTasks, MockChat, MockInterview, MockReview, MockSettings). These drift from real pages over time. Changes to real pages don't automatically appear in mock mode.

## Solution

1. Replace direct `api.js` imports with a React context (`useApi()` hook)
2. Replace `useNavigate` with `useAppNavigate` hook (adds `/debug` prefix in mock mode)
3. Mount same DoctorPage under both `/doctor/*` (real) and `/debug/doctor/*` (mock)
4. Both real and mock routes wrap in `RequireAuth` (skips auth in dev, requires login in prod). Real routes use `ApiProvider`, mock routes use `MockApiProvider`

## Architecture

```
Real App                              Mock
────────                              ────
/doctor/*                             /debug/doctor/*
  ↓                                     ↓
<RequireAuth>                         <MockApiProvider>
  <ApiProvider>                         <DoctorPage />
    <DoctorPage />                    </MockApiProvider>
  </ApiProvider>
</RequireAuth>

useApi() → real fetch()               useApi() → returns MOCK_* data
useAppNavigate("/doctor/x")           useAppNavigate("/doctor/x") → "/debug/doctor/x"
```

Both render the same `DoctorPage` component. URL determines mode — no hidden state.

**Isolation guarantee:**
- `/doctor/*` = always real data, always requires auth
- `/debug/doctor/*` = always mock data, no auth needed
- No flags, no sessionStorage, no leakage risk

## New Files

### `src/api/ApiContext.jsx`
- `ApiContext` — React context
- `ApiProvider` — wraps children, provides real api.js functions as default
- `MockApiProvider` — wraps children, provides mockApi functions. Does NOT touch useDoctorStore — real auth stays intact. RequireAuth handles access control.
- `useApi()` — hook that reads from context; also exposes `isMock` boolean

### `src/api/mockApi.js`
- Exports same function names as api.js (~35 functions for doctor pages)
- Returns `Promise.resolve(...)` with MOCK_* data from MockData.jsx
- Holds mutable in-memory state for write operations (createTask, patchTask, decideSuggestion, etc.)
- State resets on page refresh (module-level variables re-initialize)

### `src/hooks/useAppNavigate.js`
- Wraps `useNavigate` from react-router-dom
- Reads `isMock` from `useApi()`
- If mock and path starts with `/doctor`, prepends `/debug`
- Otherwise passes through unchanged

```js
export function useAppNavigate() {
  const navigate = useNavigate();
  const { isMock } = useApi();
  return (path, options) => {
    if (isMock && typeof path === "string" && path.startsWith("/doctor")) {
      navigate("/debug" + path, options);
    } else {
      navigate(path, options);
    }
  };
}
```

## Modified Files

### `src/App.jsx`
- Wrap real `/doctor/*` routes in `<ApiProvider>`
- Add `/debug/doctor/*` routes wrapping `<MockApiProvider><DoctorPage /></MockApiProvider>`
- MobileFrame already wraps both (existing pattern)
- No `RequireAuth` on debug routes

```jsx
{/* Real */}
<Route path="/doctor/*" element={<MobileFrame><RequireAuth><ApiProvider><DoctorPage /></ApiProvider></RequireAuth></MobileFrame>} />

{/* Mock — same component, mock API, auth required in prod */}
<Route path="/debug/doctor/*" element={<MobileFrame><RequireAuth><MockApiProvider><DoctorPage /></MockApiProvider></RequireAuth></MobileFrame>} />
```

### Every doctor page — two changes per file:

**Change 1: API imports → useApi hook**
```jsx
// Before:
import { getPatients, searchPatients } from "../../api";
// After:
const { getPatients, searchPatients } = useApi();
```

**Change 2: useNavigate → useAppNavigate**
```jsx
// Before:
import { useNavigate } from "react-router-dom";
const navigate = useNavigate();
// After:
import { useAppNavigate } from "../../hooks/useAppNavigate";
const navigate = useAppNavigate();
```

### Pages to migrate (ordered simplest → most complex):
1. HomePage — 1 API function, uses useNavigate
2. SettingsPage — 4 API functions, uses useNavigate
3. TasksPage — 6 API functions, uses useNavigate
4. PatientsPage — 3 API functions, uses useNavigate + useParams
5. PatientDetail — 6 API functions, uses useNavigate
6. ReviewPage — 6 API functions, uses useNavigate
7. ChatPage — 6 API functions, no useNavigate
8. InterviewPage — 7 API functions, uses useNavigate
9. DoctorPage shell — 2 API functions, uses useNavigate + useParams
10. Subpages: TemplateSubpage (3 API functions), AddKnowledgeSubpage (1 API function)

### `src/pages/doctor/debug/MockPages.jsx`
Shrinks from 742 lines to ~10 lines — just a redirect:
```jsx
/**
 * @route /debug/doctor-pages
 * Legacy entry point — redirects to /debug/doctor
 */
import { Navigate } from "react-router-dom";
export default function MockPages() {
  return <Navigate to="/debug/doctor" replace />;
}
```

The actual mock rendering is handled by the `/debug/doctor/*` routes in App.jsx.

## Deleted Files/Code

After migration is complete:
- All Mock* functions in MockPages.jsx (~500 lines)
- MockData.jsx stays (consumed by mockApi.js)
- Subpages created for mock/real bridging: evaluate each individually. Keep those that improve real page readability (e.g., ReviewSubpage separates UI from polling). Delete those that just wrap a single component.

## Mock Write Operations

mockApi.js holds mutable copies of MOCK_* arrays. Writes mutate in-memory state:

```js
let tasks = [...MOCK_TASKS];

export function createTask(doctorId, data) {
  const newTask = { id: Date.now(), ...data, status: "pending" };
  tasks = [...tasks, newTask];
  return Promise.resolve(newTask);
}

export function getTasks(doctorId, status) {
  const filtered = status ? tasks.filter(t => t.status === status) : tasks;
  return Promise.resolve({ items: filtered });
}
```

State resets on page refresh (module re-initialization).

## Complex Flows in Mock Mode

| Flow | Mock behavior |
|------|--------------|
| Interview multi-turn | Return canned steps from MOCK_INTERVIEW_STATE |
| File upload / OCR | Return fake extracted text |
| Polling (ReviewPage) | Return MOCK_SUGGESTIONS immediately |
| Export PDF | No-op success |
| Auth | RequireAuth on both real and mock routes. Dev: skipped. Prod: must be logged in. |
| Doctor store | Untouched — real auth stays. MockApiProvider only swaps the API layer. |

## What Stays Unchanged

- `api.js` — still the real implementation, consumed via context
- All shared components (RecordCard, PageSkeleton, FilterBar, etc.)
- MockData.jsx — data source, consumed by mockApi.js
- `useDoctorStore` — auth state management (seeded by MockApiProvider in mock mode)
- Patient portal (PatientPage) — separate concern, not in scope
- `useParams` — works the same under both `/doctor/:section` and `/debug/doctor/:section`

## Migration Strategy

Each page is migrated independently and tested before moving to the next. Build passes after each step. Order is simplest → most complex to validate the pattern early.

Phase 1: Foundation — ApiContext, useApi, useAppNavigate, ApiProvider, MockApiProvider
Phase 2: Migrate pages — one at a time, two changes per file (useApi + useAppNavigate), build-check each
Phase 3: Add `/debug/doctor/*` routes to App.jsx
Phase 4: Build mockApi.js with MOCK_* data
Phase 5: Wire up MockApiProvider + test mock mode end-to-end
Phase 6: Delete dead mock code (MockPages Mock* functions) + evaluate subpage cleanup
