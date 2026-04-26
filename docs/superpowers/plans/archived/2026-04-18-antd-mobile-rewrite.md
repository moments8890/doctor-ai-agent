# antd-mobile Full Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite all mobile-facing pages (doctor + patient + login) from MUI to antd-mobile, keeping admin on MUI.

**Architecture:** Clean rewrite in `src/v2/` alongside old code. Switched via `VITE_USE_V2` env variable. Old code stays for reference until validated, then deleted in Phase 3.

**Tech Stack:** antd-mobile 5.x, antd-mobile-icons, React 19, react-router-dom 7, zustand, @tanstack/react-query

**Spec:** `docs/superpowers/specs/2026-04-18-antd-mobile-rewrite-design.md`

---

## Phase 1 — Foundation + Prove It Works

### Task 1: Install Dependencies

**Files:**
- Modify: `frontend/web/package.json`

- [ ] **Step 1: Install antd-mobile and icons**

```bash
cd frontend/web
npm install antd-mobile antd-mobile-icons
```

- [ ] **Step 2: Verify build still works**

```bash
npx vite build
```
Expected: build succeeds with no errors.

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: install antd-mobile and antd-mobile-icons"
```

---

### Task 2: Create v2 Theme

**Files:**
- Create: `frontend/web/src/v2/theme.js`

- [ ] **Step 1: Create the theme file**

```js
/**
 * v2 theme — antd-mobile CSS variable configuration + font scaling.
 *
 * antd-mobile uses px values internally (not rem), so root font-size
 * multiplier does NOT cascade. We override specific CSS variables per
 * font scale tier.
 */

// ── Color mapping ──────────────────────────────────────────────────
export function applyThemeColors() {
  const r = document.documentElement.style;
  r.setProperty("--adm-color-primary", "#07C160");
  r.setProperty("--adm-color-danger", "#FA5151");
  r.setProperty("--adm-color-warning", "#FFC300");
  r.setProperty("--adm-color-success", "#07C160");
  r.setProperty("--adm-border-color", "#eee");
  r.setProperty("--adm-color-background", "#f7f7f7");
  r.setProperty("--adm-color-text", "#1A1A1A");
  r.setProperty("--adm-color-text-secondary", "#666");
  r.setProperty("--adm-color-weak", "#999");
  r.setProperty("--adm-color-light", "#ccc");
  r.setProperty("--adm-color-white", "#fff");
  r.setProperty("--adm-color-box", "#f5f5f5");
}

// App-specific tokens not covered by antd-mobile
export const APP = {
  accent: "#576B95",
  wechatGreen: "#95EC69",
  primaryLight: "#e7f8ee",
  dangerLight: "#fff0f0",
  text1: "#1A1A1A",
  text2: "#333",
  text3: "#666",
  text4: "#999",
  surface: "#fff",
  surfaceAlt: "#f7f7f7",
  border: "#eee",
  borderLight: "#f0f0f0",
};

// ── Font scaling ───────────────────────────────────────────────────
const FONT_SCALES = {
  standard:   1.0,
  large:      1.2,
  extraLarge: 1.35,
};

export function applyFontScale(tier) {
  const m = FONT_SCALES[tier] || 1.0;
  const r = document.documentElement.style;

  // antd-mobile base typography
  r.setProperty("--adm-font-size-main",  `${Math.round(14 * m)}px`);
  r.setProperty("--adm-font-size-xs",    `${Math.round(10 * m)}px`);
  r.setProperty("--adm-font-size-sm",    `${Math.round(12 * m)}px`);
  r.setProperty("--adm-font-size-md",    `${Math.round(15 * m)}px`);
  r.setProperty("--adm-font-size-lg",    `${Math.round(17 * m)}px`);
  r.setProperty("--adm-font-size-xl",    `${Math.round(20 * m)}px`);

  // Component-specific
  r.setProperty("--adm-button-font-size",    `${Math.round(15 * m)}px`);
  r.setProperty("--adm-navbar-font-size",    `${Math.round(17 * m)}px`);
  r.setProperty("--adm-list-item-font-size", `${Math.round(15 * m)}px`);
  r.setProperty("--adm-input-font-size",     `${Math.round(14 * m)}px`);
  r.setProperty("--adm-tabs-font-size",      `${Math.round(14 * m)}px`);
}

// ── Init ───────────────────────────────────────────────────────────
export function initTheme(fontScaleTier = "large") {
  applyThemeColors();
  applyFontScale(fontScaleTier);
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/v2/theme.js
git commit -m "feat(v2): add antd-mobile theme with color mapping and font scaling"
```

---

### Task 3: Create v2 Keyboard Handler

**Files:**
- Create: `frontend/web/src/v2/keyboard.js`

Reference: `frontend/web/src/hooks/useKeyboardSafeArea.js` (port all 6 concerns)

- [ ] **Step 1: Create the keyboard handler**

```js
/**
 * WeChat WebView keyboard handler.
 *
 * antd-mobile SafeArea handles only env(safe-area-inset-bottom) — the home
 * bar indicator. This hook handles the keyboard itself:
 *   1. wx.onKeyboardHeightChange (WeChat API)
 *   2. visualViewport resize fallback
 *   3. focusin/focusout fallback
 *   4. touchend + focus({ preventScroll: true }) — prevent auto-scroll
 *   5. Body scroll lock when keyboard is open
 *   6. keyboardresize custom event for chat scroll-to-bottom
 */
import { useEffect, useCallback } from "react";

export function useKeyboard() {
  useEffect(() => {
    const root = document.documentElement;
    let keyboardOpen = false;

    function setKeyboard(height) {
      const open = height > 0;
      root.style.setProperty("--keyboard-height", `${height}px`);

      if (open && !keyboardOpen) {
        document.documentElement.style.overflow = "hidden";
        document.body.style.overflow = "hidden";
      } else if (!open && keyboardOpen) {
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
      }
      keyboardOpen = open;
      setTimeout(() => window.dispatchEvent(new Event("keyboardresize")), 280);
    }

    // Global preventScroll focus interception
    const INPUT_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);
    function isInputEl(el) {
      return el && (INPUT_TAGS.has(el.tagName) || el.isContentEditable);
    }
    function onTouchEnd(e) {
      const target = e.target;
      const inputEl = isInputEl(target) ? target
        : target.closest?.("input, textarea, select, [contenteditable]");
      if (!inputEl) return;
      if (document.activeElement === inputEl) return;
      e.preventDefault();
      inputEl.focus({ preventScroll: true });
    }
    document.addEventListener("touchend", onTouchEnd, { passive: false });

    // Strategy 1: WeChat API
    if (window.wx?.onKeyboardHeightChange) {
      window.wx.onKeyboardHeightChange((res) => setKeyboard(res.height));
      return () => {
        document.removeEventListener("touchend", onTouchEnd);
        if (keyboardOpen) {
          document.documentElement.style.overflow = "";
          document.body.style.overflow = "";
        }
      };
    }

    // Strategy 2: visualViewport
    const vv = window.visualViewport;
    let vvActive = false;
    function onVVResize() {
      if (!vv) return;
      const diff = window.innerHeight - vv.height;
      setKeyboard(diff > 100 ? diff : 0);
      vvActive = true;
    }
    if (vv) vv.addEventListener("resize", onVVResize);

    // Strategy 3: focusin/focusout
    function onFocusIn(e) {
      if (isInputEl(e.target) && !vvActive) setKeyboard(300);
    }
    function onFocusOut(e) {
      if (isInputEl(e.target) && !vvActive) {
        setTimeout(() => {
          if (!isInputEl(document.activeElement)) setKeyboard(0);
        }, 100);
      }
    }
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);

    return () => {
      document.removeEventListener("touchend", onTouchEnd);
      if (vv) vv.removeEventListener("resize", onVVResize);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
      if (keyboardOpen) {
        document.documentElement.style.overflow = "";
        document.body.style.overflow = "";
      }
    };
  }, []);
}

/**
 * Scroll a ref into view when the keyboard opens/closes.
 * Usage: useScrollOnKeyboard(bottomRef)
 */
export function useScrollOnKeyboard(ref) {
  const scroll = useCallback(() => {
    ref.current?.scrollIntoView({ behavior: "smooth" });
  }, [ref]);

  useEffect(() => {
    window.addEventListener("keyboardresize", scroll);
    return () => window.removeEventListener("keyboardresize", scroll);
  }, [scroll]);
}

/**
 * CSS for keyboard-aware containers (chat pages).
 * Apply as inline style on the outermost flex container.
 */
export const keyboardAwareStyle = {
  display: "flex",
  flexDirection: "column",
  height: "calc(100% - var(--keyboard-height, 0px))",
  overflow: "hidden",
  transition: "height 0.25s cubic-bezier(0.33,1,0.68,1)",
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/v2/keyboard.js
git commit -m "feat(v2): add WeChat keyboard handler (port from useKeyboardSafeArea)"
```

---

### Task 4: Create v2 App Shell + Routing Transition

**Files:**
- Create: `frontend/web/src/v2/App.jsx`
- Modify: `frontend/web/src/App.jsx` (add VITE_USE_V2 switch)

- [ ] **Step 1: Create v2/App.jsx**

```jsx
/**
 * v2 App shell — antd-mobile ConfigProvider + SafeArea + Routes.
 * Admin routes are lazy-loaded from old pages (MUI).
 */
import { useEffect, useState, lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, SafeArea } from "antd-mobile";
import enUS from "antd-mobile/es/locales/zh-CN";
import { onAuthExpired, setWebToken, fetchDraftSummary, getTasks } from "../api";
import { queryClient } from "../lib/queryClient";
import { QK } from "../lib/queryKeys";
import { ApiProvider } from "../api/ApiContext";
import { PatientApiProvider } from "../api/PatientApiContext";
import { useDoctorStore } from "../store/doctorStore";
import { syncFontScaleFromServer, saveFontScaleToServer, useFontScaleStore } from "../store/fontScaleStore";
import { isMiniApp } from "../utils/env";
import { useKeyboard } from "./keyboard";
import { initTheme, applyFontScale } from "./theme";

// Lazy-load admin (MUI) — only loaded on /admin/* routes
const AdminLoginPage = lazy(() => import("../pages/admin/AdminLoginPage"));
const AdminPage = lazy(() => import("../pages/admin/AdminPage"));

// v2 pages (antd-mobile) — will be created in subsequent tasks
// Placeholder until pages are built:
function PlaceholderPage({ name }) {
  return <div style={{ padding: 24 }}>{name} — v2 coming soon</div>;
}

const DEV_MODE = import.meta.env.DEV;
const DEV_DOCTOR_ID = import.meta.env.VITE_DEV_DOCTOR_ID || "test_doctor";
const DEV_DOCTOR_NAME = import.meta.env.VITE_DEV_DOCTOR_NAME || "";

function RequireAuth({ children }) {
  const { accessToken } = useDoctorStore();
  if (DEV_MODE) return children;
  if (!accessToken) return <Navigate to="/login" replace />;
  return children;
}

/**
 * Mobile container — constrains to phone shape on wide screens.
 * Pure CSS, no MUI dependency.
 */
function MobileFrame({ children }) {
  return (
    <div style={{
      width: "100vw", height: "100vh",
      display: "flex", justifyContent: "center", alignItems: "center",
    }}>
      <div style={{
        width: "100%", height: "100%",
        overflow: "hidden", position: "relative",
      }}>
        {children}
      </div>
    </div>
  );
}

export default function V2App() {
  useKeyboard();
  const { accessToken, doctorId, setAuth } = useDoctorStore();

  // Init theme + font scaling
  useEffect(() => {
    const tier = useFontScaleStore.getState().fontScale || "large";
    initTheme(tier);
    return useFontScaleStore.subscribe((state) => applyFontScale(state.fontScale));
  }, []);

  // Dev mode session restore (same as old App.jsx)
  useState(() => {
    if (DEV_MODE && !doctorId) {
      setAuth(DEV_DOCTOR_ID, DEV_DOCTOR_NAME, "dev-token");
    }
  });

  // WeChat token absorption from URL params
  useState(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const did = params.get("doctor_id");
    const name = params.get("name");
    if (token && did) {
      let canonicalDid = did;
      let canonicalName = name;
      try {
        const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
        const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
        const payload = JSON.parse(atob(padded));
        if (typeof payload.doctor_id === "string" && payload.doctor_id) canonicalDid = payload.doctor_id;
        if (typeof payload.name === "string" && payload.name) canonicalName = payload.name;
      } catch {}
      setAuth(canonicalDid, canonicalName || canonicalDid, token);
      setWebToken(token);
      const url = new URL(window.location.href);
      ["token", "doctor_id", "name"].forEach((k) => url.searchParams.delete(k));
      window.history.replaceState({}, "", url.toString());
    }
  });

  // Restore token on reload
  useEffect(() => {
    if (accessToken) setWebToken(accessToken);
  }, [accessToken]);

  // Prefetch badge data + sync font scale
  useEffect(() => {
    if (!accessToken || !doctorId) return;
    queryClient.prefetchQuery({
      queryKey: QK.draftSummary(doctorId),
      queryFn: () => fetchDraftSummary(doctorId),
      staleTime: 30_000,
    });
    queryClient.prefetchQuery({
      queryKey: QK.tasks(doctorId, "pending"),
      queryFn: () => getTasks(doctorId, "pending"),
      staleTime: 60_000,
    });
    syncFontScaleFromServer(doctorId);
  }, [accessToken, doctorId]);

  // Save font scale on change
  useEffect(() => {
    if (!doctorId) return;
    return useFontScaleStore.subscribe(() => saveFontScaleToServer(doctorId));
  }, [doctorId]);

  // Handle 401
  useEffect(() => {
    onAuthExpired(() => {
      if (isMiniApp()) {
        useDoctorStore.getState().clearAuth();
        alert("会话已过期，请关闭后重新打开小程序");
        window.wx?.miniProgram?.navigateBack?.();
      } else {
        useDoctorStore.getState().clearAuth();
        window.location.href = "/login";
      }
    });
  }, []);

  return (
    <ConfigProvider locale={enUS}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          {/* v2 mobile routes */}
          <Route path="/login" element={
            <MobileFrame><PlaceholderPage name="LoginPage" /></MobileFrame>
          } />
          <Route path="/" element={<Navigate to="/doctor" replace />} />
          <Route path="/doctor/*" element={
            <MobileFrame>
              <RequireAuth>
                <ApiProvider>
                  <PlaceholderPage name="DoctorPage" />
                </ApiProvider>
              </RequireAuth>
            </MobileFrame>
          } />
          <Route path="/patient/*" element={
            <MobileFrame>
              <PatientApiProvider>
                <PlaceholderPage name="PatientPage" />
              </PatientApiProvider>
            </MobileFrame>
          } />

          {/* Admin — lazy-loaded MUI */}
          <Route path="/admin/login" element={
            <Suspense fallback={null}><AdminLoginPage /></Suspense>
          } />
          <Route path="/admin/*" element={
            <Suspense fallback={null}><AdminPage /></Suspense>
          } />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
```

- [ ] **Step 2: Add VITE_USE_V2 switch to src/App.jsx**

At the top of `frontend/web/src/App.jsx`, add the conditional import and early return:

```jsx
// At the very top of the file, before other imports:
const USE_V2 = import.meta.env.VITE_USE_V2 === "true";

// If v2 is enabled, render v2 App and skip everything else
if (USE_V2) {
  const V2App = lazy(() => import("./v2/App"));
  // Re-export at module level won't work with conditional.
  // Instead, wrap the default export:
}
```

Actually, the cleaner approach — modify the default export:

Add to `frontend/web/src/App.jsx` near the top (after existing imports):

```js
import { lazy, Suspense } from "react";
const V2App = import.meta.env.VITE_USE_V2 === "true"
  ? lazy(() => import("./v2/App"))
  : null;
```

Then wrap the default export:

```jsx
export default function App() {
  if (V2App) {
    return <Suspense fallback={null}><V2App /></Suspense>;
  }
  // ... existing App code unchanged ...
```

- [ ] **Step 3: Add antd-mobile CSS import**

In `frontend/web/src/main.jsx`, add before other imports:

```js
import "antd-mobile/es/global";
```

- [ ] **Step 4: Verify both modes work**

```bash
cd frontend/web
# Old mode (default)
npx vite build
# v2 mode
VITE_USE_V2=true npx vite build
```
Expected: both builds succeed.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/App.jsx frontend/web/src/App.jsx frontend/web/src/main.jsx
git commit -m "feat(v2): add v2 app shell with VITE_USE_V2 routing switch and lazy admin"
```

---

### Task 5: Icon Mapping Audit

**Files:**
- Create: `frontend/web/src/v2/icon-map.md` (reference doc, not code)

- [ ] **Step 1: Generate list of all MUI icon imports**

```bash
cd frontend/web
grep -rh "from ['\"]@mui/icons-material" src/ | sed "s/.*import //;s/ from.*//" | sort -u > /tmp/mui-icons.txt
cat /tmp/mui-icons.txt
```

- [ ] **Step 2: For each icon, find antd-mobile-icons equivalent**

Check antd-mobile-icons package: `node -e "console.log(Object.keys(require('antd-mobile-icons')))"` or browse the npm page.

Create `frontend/web/src/v2/icon-map.md` documenting:
- Each MUI icon name → antd-mobile-icons name (if exists)
- "SVG" if no equivalent and semantically important
- "DROP" if purely decorative

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/icon-map.md
git commit -m "docs(v2): complete icon mapping audit (149 MUI → antd-mobile-icons)"
```

---

### Task 6: Build LoginPage (v2)

**Files:**
- Create: `frontend/web/src/v2/pages/login/LoginPage.jsx`
- Modify: `frontend/web/src/v2/App.jsx` (replace placeholder)

Reference: `frontend/web/src/pages/LoginPage.jsx` (business logic, API calls)

- [ ] **Step 1: Create LoginPage with antd-mobile components**

Rewrite the login page using:
- `Form`, `Input` (antd-mobile) instead of MUI TextField
- `Button` (antd-mobile) instead of AppButton
- `Tabs` (antd-mobile) instead of MUI Tabs
- `Toast.show()` for error/success messages
- `SpinLoading` instead of CircularProgress
- Plain `<div>` / `<p>` instead of Box / Typography

Port ALL business logic from old LoginPage:
- Doctor/patient tab switching
- Login with nickname + passcode
- Register doctor with invite code
- Register patient with doctor selection
- `saveSession()`, `setAuth()`, navigate on success
- All error handling

- [ ] **Step 2: Wire into v2/App.jsx**

Replace the LoginPage placeholder route with:
```jsx
import LoginPage from "./pages/login/LoginPage";
// In routes:
<Route path="/login" element={<MobileFrame><LoginPage /></MobileFrame>} />
```

- [ ] **Step 3: Test**

```bash
VITE_USE_V2=true npx vite build
```
Then test login flow manually in dev mode.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/v2/pages/login/
git commit -m "feat(v2): rewrite LoginPage with antd-mobile"
```

---

### Task 7: Build Doctor Shell (DoctorPage)

**Files:**
- Create: `frontend/web/src/v2/pages/doctor/DoctorPage.jsx`
- Modify: `frontend/web/src/v2/App.jsx` (replace placeholder)

Reference: `frontend/web/src/pages/doctor/DoctorPage.jsx` (routing, tab nav, state)

- [ ] **Step 1: Create DoctorPage shell**

Build the shell that holds all doctor subpages:
- `TabBar` (antd-mobile) for bottom navigation (我的AI / 患者 / 审核 / 任务)
- `NavBar` (antd-mobile) for top bar
- `SafeArea` (antd-mobile) for home bar
- Route outlet for subpages (using react-router `<Outlet>` or conditional rendering)
- Badge counts on tab icons
- Port auth state, section routing, and state management from old DoctorPage

Initially render placeholder `<div>`s for each section — real pages come in
subsequent tasks.

- [ ] **Step 2: Wire into v2/App.jsx**

Replace doctor placeholder with DoctorPage and subroutes:
```jsx
import DoctorPage from "./pages/doctor/DoctorPage";
```

- [ ] **Step 3: Test build + navigation**

```bash
VITE_USE_V2=true npx vite build
```
Test: login → doctor shell → tab switching works.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/
git commit -m "feat(v2): add DoctorPage shell with TabBar + NavBar"
```

---

### Task 8: Build ChatComposer + ChatBubble Wrappers

**Files:**
- Create: `frontend/web/src/v2/ChatComposer.jsx`
- Create: `frontend/web/src/v2/ChatBubble.jsx`

These are the only two wrapper components in v2. Used by 5 chat pages.

- [ ] **Step 1: Create ChatComposer**

```jsx
/**
 * Chat input bar — TextArea autoSize + voice mic + suggestion chips + send.
 * Used by all 5 chat pages.
 */
import { useRef } from "react";
import { TextArea, Button, SafeArea } from "antd-mobile";
import { SendOutline } from "antd-mobile-icons";
import { isInMiniapp } from "../utils/miniappBridge";
import { useVoiceInput } from "../hooks/useVoiceInput";
import { APP } from "./theme";

export default function ChatComposer({
  value, onChange, onSend, disabled, placeholder = "请输入...",
  doctorId, suggestions, selectedSuggestions, onToggleSuggestion,
}) {
  const inputRef = useRef(null);
  const { micButton, voiceActive } = doctorId
    ? useVoiceInput({ doctorId, value, setValue: onChange, compact: true })
    : { micButton: null, voiceActive: false };

  function handleSend() {
    if (!value.trim() && (!selectedSuggestions || selectedSuggestions.length === 0)) return;
    onSend();
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent?.isComposing) {
      e.preventDefault();
      handleSend();
    }
  }

  const canSend = value.trim() || (selectedSuggestions && selectedSuggestions.length > 0);

  return (
    <div style={{
      borderTop: `1px solid ${APP.border}`,
      background: APP.surface,
      padding: "8px 8px 0",
      flexShrink: 0,
    }}>
      {/* Suggestion chips */}
      {suggestions && suggestions.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {suggestions.map((s, i) => (
            <span key={i} onClick={() => onToggleSuggestion?.(s)}
              style={{
                padding: "4px 10px", borderRadius: 12,
                fontSize: "var(--adm-font-size-sm)",
                background: selectedSuggestions?.includes(s) ? APP.primaryLight : APP.surfaceAlt,
                color: selectedSuggestions?.includes(s) ? "#07C160" : APP.text2,
                cursor: "pointer",
              }}>
              {s}
            </span>
          ))}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 6 }}>
        {isInMiniapp() && micButton}
        <div style={{ flex: 1 }}>
          <TextArea
            ref={inputRef}
            value={value}
            onChange={onChange}
            onKeyDown={handleKeyDown}
            placeholder={voiceActive ? "正在识别…" : placeholder}
            disabled={disabled || voiceActive}
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={{ "--font-size": "var(--adm-font-size-main)" }}
          />
        </div>
        <Button
          color="primary" size="small" shape="rounded"
          disabled={!canSend || disabled}
          onClick={handleSend}
          style={{ flexShrink: 0, marginBottom: 4 }}
        >
          <SendOutline />
        </Button>
      </div>
      <SafeArea position="bottom" />
    </div>
  );
}
```

- [ ] **Step 2: Create ChatBubble**

```jsx
/**
 * Chat message bubble — user (green) or AI (white + markdown).
 */
import ReactMarkdown from "react-markdown";
import { APP } from "./theme";

export default function ChatBubble({ role, content, timestamp }) {
  const isUser = role === "user";
  return (
    <div style={{
      display: "flex",
      flexDirection: isUser ? "row-reverse" : "row",
      alignItems: "flex-end",
      gap: 8, padding: "0 12px",
    }}>
      {/* Avatar placeholder — plain div with initial */}
      <div style={{
        width: 32, height: 32, borderRadius: "50%",
        background: isUser ? "#ddd" : APP.primaryLight,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: "var(--adm-font-size-sm)", color: APP.text3,
        flexShrink: 0,
      }}>
        {isUser ? "我" : "AI"}
      </div>
      <div style={{
        maxWidth: "75%", padding: "8px 12px",
        borderRadius: isUser ? "12px 12px 0 12px" : "12px 12px 12px 0",
        background: isUser ? APP.wechatGreen : "#fff",
        fontSize: "var(--adm-font-size-main)",
        lineHeight: 1.7, whiteSpace: "pre-wrap",
      }}>
        {isUser ? content : <ReactMarkdown>{content}</ReactMarkdown>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/web/src/v2/ChatComposer.jsx frontend/web/src/v2/ChatBubble.jsx
git commit -m "feat(v2): add ChatComposer and ChatBubble shared components"
```

---

### Task 9: Build IntakePage (Chat) — Phase 1 Gate

**Files:**
- Create: `frontend/web/src/v2/pages/doctor/IntakePage.jsx`
- Modify: `frontend/web/src/v2/pages/doctor/DoctorPage.jsx` (wire subpage)

Reference: `frontend/web/src/pages/doctor/IntakePage.jsx` (all business logic, API calls, state)

This is the **Phase 1 gate** — must work in WeChat WebView on real device.

- [ ] **Step 1: Create IntakePage**

Build from scratch using:
- `NavBar` for header ("新建病历" + back + help)
- `ChatBubble` for messages
- `ChatComposer` for input (TextArea autoSize + voice + suggestions)
- `Dialog.confirm()` for exit confirmation
- `SpinLoading` for loading state
- `keyboardAwareStyle` from keyboard.js on the outer container
- `useScrollOnKeyboard(bottomRef)` for scroll-to-bottom

Port ALL business logic from old IntakePage:
- `doctorIntakeTurn`, `doctorIntakeConfirm`, `doctorIntakeCancel`
- Session state, progress tracking, carry-forward, import items
- Field review, intake complete dialog
- All error handling

- [ ] **Step 2: Wire into DoctorPage**

Add IntakePage as a subpage route inside DoctorPage.

- [ ] **Step 3: Build and test**

```bash
VITE_USE_V2=true npx vite build
```

- [ ] **Step 4: Test in WeChat WebView on real device**

Verify:
- Keyboard opens → header stays visible, chat content shrinks
- TextArea auto-grows up to 4 lines
- Send message → AI responds → chat scrolls to bottom
- Safe area padding at bottom
- Voice input works (if in miniapp)

**GATE: All 4 checks pass on iOS + Android before proceeding to Phase 2.**

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/v2/pages/doctor/IntakePage.jsx
git commit -m "feat(v2): rewrite IntakePage with antd-mobile — Phase 1 gate"
```

---

## Phase 2 — Remaining Pages

Each task follows the same pattern: create the page from scratch using antd-mobile + raw HTML, port ALL business logic from the old page, test build.

### Task 10: PatientsPage + PatientDetail

**Files:**
- Create: `frontend/web/src/v2/pages/doctor/PatientsPage.jsx`
- Create: `frontend/web/src/v2/pages/doctor/PatientDetail.jsx`

**antd-mobile components:** `List`, `List.Item`, `SearchBar`, `NavBar`, `Card`, `Dialog.confirm()`, `Popup`, `TextArea`, `Button`, `Tag`, `SpinLoading`, `ErrorBlock`

**Business logic to port from:**
- `frontend/web/src/pages/doctor/PatientsPage.jsx` — patient list, search, import, intake launch
- `frontend/web/src/pages/doctor/patients/PatientDetail.jsx` — message timeline, reply input, draft editing, teach flow

**Chat features:** PatientDetail uses ChatComposer for reply input + ChatBubble for messages.

---

### Task 11: MyAIPage

**Files:**
- Create: `frontend/web/src/v2/pages/doctor/MyAIPage.jsx`

**antd-mobile components:** `List`, `List.Item`, `Card`, `NavBar`, `Button`

**Business logic from:** `frontend/web/src/pages/doctor/MyAIPage.jsx` — AI identity dashboard, knowledge count, quick actions, persona summary

---

### Task 12: ReviewPage + ReviewQueuePage

**Files:**
- Create: `frontend/web/src/v2/pages/doctor/ReviewPage.jsx`
- Create: `frontend/web/src/v2/pages/doctor/ReviewQueuePage.jsx`

**antd-mobile components:** `List`, `List.Item`, `CapsuleTabs`, `Card`, `Collapse`, `NavBar`, `Button`, `Dialog.confirm()`, `Tag`, `TextArea`

**Business logic from:**
- `frontend/web/src/pages/doctor/ReviewPage.jsx` — diagnosis review, field editing, approval/rejection
- `frontend/web/src/pages/doctor/ReviewQueuePage.jsx` — review queue with filters

---

### Task 13: TaskPage

**Files:**
- Create: `frontend/web/src/v2/pages/doctor/TaskPage.jsx`

**antd-mobile components:** `List`, `List.Item`, `CapsuleTabs`, `NavBar`, `Popup`, `Form`, `Input`, `Button`

**Business logic from:** `frontend/web/src/pages/doctor/TaskPage.jsx` — task list, filters, task creation, task detail

---

### Task 14: SettingsPage + Subpages

**Files:**
- Create: `frontend/web/src/v2/pages/doctor/SettingsPage.jsx`
- Create: `frontend/web/src/v2/pages/doctor/settings/PersonaSubpage.jsx`
- Create: `frontend/web/src/v2/pages/doctor/settings/KnowledgeSubpage.jsx`
- Create: `frontend/web/src/v2/pages/doctor/settings/KnowledgeDetailSubpage.jsx`
- Create: `frontend/web/src/v2/pages/doctor/settings/AddKnowledgeSubpage.jsx`
- Create: `frontend/web/src/v2/pages/doctor/settings/SettingsListSubpage.jsx`

**antd-mobile components:** `List`, `List.Item`, `NavBar`, `TextArea`, `Button`, `Dialog.confirm()`, `Popup`, `Switch`, `Form`, `Input`

**Business logic from:** `frontend/web/src/pages/doctor/SettingsPage.jsx` and all subpages in `subpages/`

---

### Task 15: OnboardingWizard

**Files:**
- Create: `frontend/web/src/v2/pages/doctor/OnboardingWizard.jsx`

**antd-mobile components:** `Steps`, `Button`, `Form`, `Input`, `TextArea`, `NavBar`

**Business logic from:** `frontend/web/src/pages/doctor/OnboardingWizard.jsx`

---

### Task 16: Patient Shell (PatientPage)

**Files:**
- Create: `frontend/web/src/v2/pages/patient/PatientPage.jsx`

**antd-mobile components:** `TabBar`, `NavBar`, `SafeArea`

**Business logic from:** `frontend/web/src/pages/patient/PatientPage.jsx` — tab nav, auth, bottom navigation

---

### Task 17: Patient ChatTab

**Files:**
- Create: `frontend/web/src/v2/pages/patient/ChatTab.jsx`

**antd-mobile components:** Uses `ChatComposer` + `ChatBubble` + `List`, `Card`, `SpinLoading`

**Business logic from:** `frontend/web/src/pages/patient/ChatTab.jsx` — message polling, send, quick actions, triage rendering

---

### Task 18: Patient IntakePage

**Files:**
- Create: `frontend/web/src/v2/pages/patient/IntakePage.jsx`

**antd-mobile components:** Uses `ChatComposer` + `ChatBubble` + `NavBar`, `Button`, `Dialog.confirm()`, `Popup`

**Business logic from:** `frontend/web/src/pages/patient/IntakePage.jsx` — intake session, suggestions, summary, confirm

---

## Phase 3 — Cleanup

### Task 19: Audit Admin Imports + Delete Old Code

**Files:**
- Modify: `frontend/web/src/pages/admin/` (move shared component imports if needed)
- Delete: `frontend/web/src/pages/doctor/`
- Delete: `frontend/web/src/pages/patient/`
- Delete: `frontend/web/src/pages/LoginPage.jsx`
- Delete: `frontend/web/src/components/` (except admin-needed components)
- Delete: `frontend/web/src/theme.js`
- Delete: `frontend/web/src/hooks/useKeyboardSafeArea.js`
- Delete: `frontend/web/src/hooks/useNavDirection.js`

- [ ] **Step 1: Audit admin imports**

```bash
grep -rh "from.*components/" frontend/web/src/pages/admin/ | sort -u
```

For any shared components admin still imports, copy them to `frontend/web/src/pages/admin/components/` and update imports.

- [ ] **Step 2: Delete old mobile pages and components**

- [ ] **Step 3: Flatten v2**

Move `frontend/web/src/v2/*` → `frontend/web/src/` (theme.js, keyboard.js, App.jsx, pages/)

- [ ] **Step 4: Update App.jsx**

Remove the `VITE_USE_V2` switch — v2 is now the only path.

- [ ] **Step 5: Remove unused dependencies**

```bash
cd frontend/web
npm uninstall @mui/icons-material framer-motion
```

Keep `@mui/material` and `@emotion/*` (admin needs them).

- [ ] **Step 6: Verify build + bundle size**

```bash
npx vite build
```
Compare bundle size to pre-rewrite baseline.

- [ ] **Step 7: Update CLAUDE.md**

Update the "UI Design System" section to reflect antd-mobile components instead of MUI wrappers.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: cleanup — remove old MUI pages/components, flatten v2"
```

---

### Task 20: Dropped Component Decisions

Before finalizing Phase 3, review each dropped component:

| Component | Decision |
|-----------|----------|
| `ErrorBoundary` | Add React error boundary or accept? |
| `CitationPopover` | Inline text OK or need antd-mobile Popover? |
| `MsgAvatar` / `NameAvatar` | Plain div OK or need styled component? |
| `IconBadge` | Plain span OK or need styled component? |
| `SlideOverlay` / transitions | Any transitions needed? |

User decides for each. Implement decisions as needed.
