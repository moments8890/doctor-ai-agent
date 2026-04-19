# MUI → antd-mobile Full Rewrite Design Spec

**Date:** 2026-04-18
**Status:** Draft (rev 2 — addresses Claude + Codex review feedback)
**Scope:** UI rewrite of mobile doctor/patient pages from MUI to antd-mobile.
Admin pages stay on MUI.

## Problem

The current frontend uses MUI 7 (Material Design, desktop-first) inside WeChat
miniprogram's `<web-view>`. This causes constant friction:

- Keyboard handling broken (headers pushed off-screen, inputs hidden)
- `position: fixed` unreliable in WeChat WebView
- Safe area padding requires custom hooks
- TextArea auto-grow requires custom hooks
- MUI components designed for desktop Material Design, not Chinese mobile apps
- Bundle size: ~530KB gzipped for MUI + Emotion (35-40% of total)
- 51 custom wrapper components exist just to make MUI behave on mobile

## Solution

Rewrite mobile-facing pages (doctor + patient) using antd-mobile — the consensus
React mobile UI framework in China (12k GitHub stars, 10 years maintained by
Alibaba). Admin pages stay on MUI (desktop-appropriate).

## Scope Boundary

| Surface | Framework | Reason |
|---------|-----------|--------|
| Doctor pages (WeChat WebView) | antd-mobile (rewrite) | Mobile-first, Chinese design |
| Patient pages (WeChat WebView) | antd-mobile (rewrite) | Mobile-first, Chinese design |
| Admin pages (desktop browser) | MUI (keep as-is) | Desktop data tables, autocomplete, tooltips — antd-mobile has no equivalents |
| Login page | antd-mobile (rewrite) | Shared entry point, mobile-first |

Admin uses `Table`, `Autocomplete`, `Tooltip`, `Snackbar`, `Switch`, dark theme,
hover states — all desktop patterns with no antd-mobile equivalent. Admin routes
are lazy-loaded, so MUI only loads when `/admin/*` is hit.

## Architecture

### Directory Structure

```
src/
  api/          ← KEEP (shared, unchanged)
  store/        ← KEEP (shared, unchanged)
  lib/          ← KEEP (shared, unchanged)
  utils/        ← KEEP (shared, unchanged)

  pages/        ← OLD — untouched, reference only during rewrite
  components/   ← OLD — untouched, reference only during rewrite
  theme.js      ← OLD — reference only
  hooks/        ← OLD — reference only

  v2/
    theme.js            ← antd-mobile CSS variable config + font scaling
    keyboard.js         ← WeChat keyboard handler (simplified from useKeyboardSafeArea)
    App.jsx             ← ConfigProvider + SafeArea + Routes
    pages/
      login/            ← LoginPage
      doctor/           ← DoctorPage shell + all doctor subpages
      patient/          ← PatientPage shell + all patient subpages
```

Admin pages remain at `src/pages/admin/` on MUI — routed via lazy import.

### What Stays (reuse as-is)

| Directory | Contents |
|-----------|----------|
| `src/api/` | ApiContext, PatientApiContext, all API functions |
| `src/store/` | zustand stores (doctorStore, fontScaleStore) |
| `src/lib/` | queryClient, queryKeys, doctorQueries |
| `src/utils/` | miniappBridge, doctorBasePath, time, env |
| `src/pages/admin/` | Admin pages (MUI, unchanged) |
| `src/hooks/useVoiceInput.js` | Voice recording + ASR (not MUI-dependent) |
| `react-markdown` | AI message rendering in chat bubbles |

### What Gets Deleted (after v2 validated)

| Item | Reason |
|------|--------|
| `src/pages/doctor/`, `src/pages/patient/`, `src/pages/LoginPage.jsx` | Replaced by v2 |
| `src/components/` (51 files) | Replaced by antd-mobile or minimal v2 wrappers. **Exception:** any components still imported by admin pages are kept until admin is independently migrated. |
| `src/theme.js` | Replaced by v2 theme |
| `src/hooks/useNavDirection.js` | No custom page transitions in v2 |
| `@mui/icons-material` | Removed from package.json |

**Note:** `@mui/material` and `@emotion/*` stay — required by admin pages
(MUI v7 requires Emotion as its styling engine). Bundle impact is reduced
via lazy-loading admin routes (added as explicit Phase 3 task).

## Dependencies

### Add

| Package | Purpose |
|---------|---------|
| `antd-mobile` | UI component library (~200KB gzipped) |
| `antd-mobile-icons` | Icon library (~217 icons) |

### Keep

| Package | Reason |
|---------|--------|
| `@mui/material` | Admin pages |
| `react-markdown` | AI message rendering |
| `framer-motion` | Remove in Phase 3. Current `useReducedMotion()` usage is replaced by CSS `@media (prefers-reduced-motion: reduce)`. No page transitions in v2, so framer-motion has no remaining purpose. |
| `@emotion/react`, `@emotion/styled` | Keep — required by MUI v7 for admin pages |
| `zustand` | Global state (font scale, doctor store) |
| `@tanstack/react-query` | API state management |

### Remove (after validation)

| Package | Savings |
|---------|---------|
| `@mui/icons-material` | ~150KB gzipped |

**Expected bundle reduction:** ~150KB gzipped from icons. Additional savings
from lazy-loading MUI (only loaded on `/admin/*`).

## Theme & Font Scaling

antd-mobile CSS variables as primary design system. Font scaling is first-class.

### Color mapping

```js
// v2/theme.js
const root = document.documentElement.style;
root.setProperty("--adm-color-primary", "#07C160");     // WeChat green
root.setProperty("--adm-color-danger", "#FA5151");
root.setProperty("--adm-color-warning", "#FFC300");
root.setProperty("--adm-color-success", "#07C160");
root.setProperty("--adm-border-color", "#eee");
root.setProperty("--adm-color-background", "#f7f7f7");  // surfaceAlt
root.setProperty("--adm-color-text", "#1A1A1A");         // text1

// App-specific tokens not covered by antd-mobile
export const APP_COLORS = {
  accent: "#576B95",        // WeChat blue, links, secondary actions
  wechatGreen: "#95EC69",   // user chat bubble
  text2: "#333",
  text3: "#666",
  text4: "#999",
};
```

### Font scaling (3 tiers)

antd-mobile uses `px` values internally, not `rem`. Root font-size multiplier
does NOT cascade into antd-mobile components. We must override specific CSS
variables per tier.

```js
const FONT_SCALES = {
  standard: { multiplier: 1.0 },
  large:    { multiplier: 1.2 },
  extraLarge: { multiplier: 1.35 },
};

function applyFontScale(tier) {
  const m = FONT_SCALES[tier].multiplier;
  const root = document.documentElement.style;

  // antd-mobile typography CSS variables (exhaustive list)
  root.setProperty("--adm-font-size-main",  `${Math.round(14 * m)}px`);
  root.setProperty("--adm-font-size-xs",    `${Math.round(10 * m)}px`);
  root.setProperty("--adm-font-size-sm",    `${Math.round(12 * m)}px`);
  root.setProperty("--adm-font-size-md",    `${Math.round(15 * m)}px`);
  root.setProperty("--adm-font-size-lg",    `${Math.round(17 * m)}px`);
  root.setProperty("--adm-font-size-xl",    `${Math.round(20 * m)}px`);

  // Component-specific size overrides
  root.setProperty("--adm-button-font-size", `${Math.round(15 * m)}px`);
  root.setProperty("--adm-navbar-font-size", `${Math.round(17 * m)}px`);
}
```

Font scale tier is persisted in `fontScaleStore` (zustand). `applyFontScale()`
is called on app init and when the user changes the setting.

## Keyboard Handling (CRITICAL)

**antd-mobile `SafeArea` handles only `env(safe-area-inset-bottom)` — the home
bar indicator. It does NOT handle keyboard height, body scroll lock, or focus
interception.**

The current `useKeyboardSafeArea.js` handles 5 distinct concerns:
1. `wx.onKeyboardHeightChange` (WeChat API) — keyboard height detection
2. `visualViewport` resize fallback — Safari/Chrome detection
3. `focusin/focusout` fallback — boolean keyboard detection
4. `touchend` + `focus({ preventScroll: true })` — prevent auto-scroll on focus
5. Body scroll lock when keyboard is open
6. `keyboardresize` custom event for chat scroll-to-bottom

**v2 plan:** Create `v2/keyboard.js` — a simplified version of the current hook
that retains concerns 1-6 above. Use antd-mobile `SafeArea` only for the home
bar inset. The keyboard handler is platform plumbing, not a UI component.

Chat pages use `TextArea autoSize` (antd-mobile native) for auto-growing input.
No `useAutoGrow` hook needed.

## Component Mapping

### Principle

Use raw antd-mobile components directly where they match. Create minimal
wrapper components only where app-specific behavior requires it (navigation
shell, chat composer). Where antd-mobile has no equivalent, use plain HTML —
user decides how to add back later.

### antd-mobile Direct Replacement

| Old Component | antd-mobile Replacement |
|---------------|------------------------|
| `AppButton` | `Button` |
| `ConfirmDialog` | `Dialog.confirm()` (imperative API — callsites change from declarative `<ConfirmDialog open>` to imperative `Dialog.confirm({})`) |
| `SheetDialog` | `Popup` position="bottom" (note: not swipeable — `Popup` lacks swipe-to-dismiss) |
| `Toast` hook | `Toast.show()` |
| `SectionLoading` | `Skeleton` |
| `EmptyState` | `ErrorBlock` status="empty" |
| `PullToRefresh` | `PullToRefresh` |
| `SubpageHeader` | `NavBar` |
| `ListCard` | `List` + `List.Item` (prefix=avatar, description=subtitle, extra=right — layout is less flexible than current ListCard) |
| `FilterBar` | `CapsuleTabs` (no dividers prop — style via CSS) |
| `ActionPanel` | `ActionSheet` |
| `RecordCard` | `Card` + `Collapse` |
| `TextField` | `Input` / `TextArea` (autoSize built in) |
| `CircularProgress` | `SpinLoading` / `DotLoading` |
| `Chip` | `Tag` |
| `HelpTip` | `Popover` |
| MUI `Box` (1,737 uses) | `<div>` with inline style or className |
| MUI `Typography` (1,127 uses) | `<span>` / `<p>` with inline style |
| MUI `Dialog` | `Dialog` / `Popup` |
| MUI `Tabs` | `Tabs` |
| MUI `Skeleton` | `Skeleton` |

### Minimal v2 Wrappers (app-specific behavior)

These are kept as thin wrappers because they encode app-specific logic:

| Wrapper | Why needed |
|---------|-----------|
| `ChatComposer` | TextArea autoSize + voice mic + suggestion chips + send button. Repeated in 5 chat pages. |
| `ChatBubble` | User/AI bubble styling + react-markdown for AI messages. Repeated in 5 chat pages. |

All other components use raw antd-mobile or raw HTML directly.

### Platform Features

| Custom Code | v2 Replacement |
|-------------|----------------|
| `useKeyboardSafeArea` hook | `v2/keyboard.js` (simplified, keeps WeChat-specific logic) |
| `useAutoGrow` hook | `TextArea autoSize` (antd-mobile native) |
| `useScrollOnKeyboard` hook | `v2/keyboard.js` `keyboardresize` event |
| `KEYBOARD_AWARE_CONTAINER` | `v2/keyboard.js` + `SafeArea` for home bar |

### Voice Input

`useVoiceInput` hook and voice recording logic are not MUI-dependent. They
stay as-is. Chat pages in v2 import the hook and render the mic button.

### AI Message Rendering

`react-markdown` stays. Chat bubbles render AI responses via `<ReactMarkdown>`.
No change to markdown rendering.

### Icons

| Old | New |
|-----|-----|
| `@mui/icons-material` (149 imports) | `antd-mobile-icons` |

**Prerequisite before page rewrites:** complete icon mapping audit.

For each of the 149 MUI icon imports, document:
- antd-mobile-icons equivalent (if exists)
- Inline SVG needed (if no equivalent and semantically important)
- Drop (if purely decorative)

This audit is Phase 1 work, not deferred to page rewrites.

### Dropped (plain HTML, add back later)

| Component | v2 Fallback |
|-----------|-------------|
| `MsgAvatar` / `NameAvatar` | `<div>` with initials |
| `IconBadge` | `<span>` with text |
| `SlideOverlay` / page transitions | Instant mount, no animation |
| `CitationPopover` | Inline text |
| `StatColumn` | Plain text |
| `ErrorBoundary` | Omit (add back later) |

## Page Rewrite Order

### Phase 1 — Foundation + Prove It Works

1. Install `antd-mobile`, `antd-mobile-icons`
2. Create `v2/theme.js` — CSS variable config + font scaling
3. Create `v2/keyboard.js` — WeChat keyboard handler
4. Create `v2/App.jsx` — ConfigProvider + SafeArea + Routes
5. **Routing transition:** Top-level `src/App.jsx` uses an env variable
   `VITE_USE_V2=true` (default false). When true, doctor/patient/login routes
   point to `v2/pages/*`; admin always points to old `pages/admin/*`. This
   enables per-deploy switching and instant rollback by flipping the env var.
6. Complete icon mapping audit (149 icons → antd-mobile-icons / SVG / drop)
7. **Lazy-load admin routes** — wrap admin imports in `React.lazy()` so MUI
   is only loaded when `/admin/*` is hit. This must happen before v2 goes live.
8. Build `LoginPage` — proves auth flow + antd-mobile Form/Button pattern
9. Build Doctor shell (`DoctorPage` — NavBar + TabBar + route outlet)
10. Build `InterviewPage` (chat) inside the shell — **prove keyboard, TextArea
   autoSize, SafeArea, and chat scroll all work on real WeChat WebView device**

**Gate:** LoginPage → DoctorPage shell → InterviewPage all work correctly in
WeChat WebView on iOS + Android before proceeding to Phase 2.

### Phase 2 — Remaining Pages

| Order | Page | Complexity |
|-------|------|------------|
| 1 | `PatientsPage` + `PatientDetail` (reply chat) | High |
| 2 | `MyAIPage` | Low |
| 3 | `ReviewPage` + `ReviewQueuePage` | Medium |
| 4 | `TaskPage` | Medium |
| 5 | `SettingsPage` + subpages | Medium |
| 6 | `OnboardingWizard` | Low |
| 7 | Patient `PatientPage` (shell + tabs) | Medium |
| 8 | Patient `ChatTab` | Medium |
| 9 | Patient `InterviewPage` | Medium |

### Phase 3 — Cleanup

1. Delete old `src/pages/doctor/`, `src/pages/patient/`, `src/pages/LoginPage.jsx`
2. Delete `src/components/` — **except** components still imported by admin pages.
   Audit admin imports first; move any shared components admin needs to
   `src/pages/admin/components/` before deleting the rest.
3. Delete old `src/theme.js`, `src/hooks/useKeyboardSafeArea.js`,
   `src/hooks/useNavDirection.js`
4. Move `src/v2/*` → `src/` (flatten)
5. Remove `@mui/icons-material` from package.json
6. Lazy-load MUI for admin routes (if not already)
7. Remove `framer-motion` if no longer used
8. Verify bundle size

## Testing & Validation

**Per-page:** `vite build` compiles, visual check in Chrome mobile mode,
API calls work, forms submit.

**E2E selector strategy:** Current tests use `getByText("label")` extensively
(not `getByRole("button")` — per CLAUDE.md, AppButton renders as `<div>`).
antd-mobile components render standard HTML elements, so `getByText` selectors
should still work. Selectors that target MUI-specific class names or
`data-testid` attributes will need updating.

**Final validation:**
1. Existing E2E Playwright suite passes against v2
2. QA walkthrough in WeChat miniprogram on real device (iOS + Android)
3. Bundle size comparison

**No new tests during rewrite.** UI-layer swap, not behavior change. Existing
E2E tests are the validation gate.

**Rollback:** Set `VITE_USE_V2=false` in env and redeploy. Old pages are
intact until Phase 3 cleanup. During Phase 1-2, both old and v2 pages coexist
in the bundle, switched by the env variable. Rollback is a config change, not
a code revert.

## Dropped Components — Acceptance Criteria

Components dropped to plain HTML in v2 are intentional regressions. Each must
have a decision recorded before Phase 3 cleanup:

| Component | Decision needed by |
|-----------|-------------------|
| `ErrorBoundary` | Phase 2 end — add React error boundary or accept unhandled errors |
| `CitationPopover` | Phase 2 end — inline text is acceptable or needs antd-mobile Popover |
| `MsgAvatar` / `NameAvatar` | Phase 2 end — plain div acceptable or needs styled component |
| `IconBadge` | Phase 2 end — plain span acceptable or needs styled component |
| `SlideOverlay` / page transitions | Phase 3 — decide if any transitions are needed |

User reviews each at Phase 2 end and decides: keep plain HTML or build native.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Keyboard regression in WeChat WebView | Critical | Keep custom keyboard handler (v2/keyboard.js). Validate on real device at Phase 1 gate. |
| antd-mobile component doesn't match needed behavior | Medium | Fall back to plain HTML, solve later |
| Font scaling breaks antd-mobile components | Medium | Override all 8+ font-size CSS variables per tier. Test each tier on every page. |
| antd-mobile-icons missing needed icons | Medium | Icon mapping audit in Phase 1. Use inline SVG for gaps. |
| React 19 + antd-mobile v5 compatibility | Medium | Test in Phase 1 foundation. If issues, pin antd-mobile version. |
| Popup lacks swipe-to-dismiss (vs SwipeableDrawer) | Medium | Evaluate `@use-gesture/react` in Phase 1 component evaluation. Core WeChat UX convention — cannot defer indefinitely. |
| Bundle size increases during dual-dependency period | Low | Temporary; admin lazy-loaded in Phase 1 step 7 |
| E2E tests break due to selector changes | Low | Update selectors; getByText still works |
| Dialog.confirm() imperative API differs from declarative ConfirmDialog | Low | Mechanical refactor at each callsite |
| Admin pages share components being deleted | Low | Audit admin imports in Phase 3; move needed components to admin subdir before deleting |

## Cascading Impact

Per repo policy (AGENTS.md), changes that touch the UI layer cascade to:

- **E2E tests** — selector updates needed (Phase 3)
- **CLAUDE.md UI Design System section** — must be updated to reflect antd-mobile
  components instead of MUI wrappers
- **WeChat miniprogram** — must be tested on real device (Phase 1 gate)
- **Font scaling** — must work at all 3 tiers (Phase 1 foundation)
