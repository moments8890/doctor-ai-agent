import "antd-mobile/es/global";
import "./index.css";
import React, { useMemo } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, MemoryRouter } from "react-router-dom";
import { CssBaseline, ThemeProvider } from "@mui/material";
import App from "./v2/App";
import { applyFontScale, createAppThemeScaled } from "./theme";
import { useFontScaleStore, useFontScaleRerender, triggerFontScaleRerender } from "./store/fontScaleStore";
import { setLocale, t } from "./i18n";
import { buildTitle } from "./lib/pageTitle";

setLocale("zh-CN");
document.documentElement.lang = "zh-CN";
document.title = buildTitle(null, t("app.title"));

// Router selection by build mode:
//   - native (Capacitor iOS/Android, WeChat miniapp): MemoryRouter — no
//     URL bar, no deep-linking, hide internal paths.
//   - everything else (web dev, web prod): BrowserRouter — URLs work,
//     refresh-to-route works, /login is reachable directly, E2E tests
//     can navigate by path.
//
// Override either way with VITE_ROUTER_MODE=browser|memory if needed.
const _OVERRIDE = import.meta.env.VITE_ROUTER_MODE;
const _IS_NATIVE_BUILD = ["ios", "android", "miniapp"].includes(import.meta.env.MODE);
const Router =
  _OVERRIDE === "browser" ? BrowserRouter
  : _OVERRIDE === "memory" ? MemoryRouter
  : _IS_NATIVE_BUILD ? MemoryRouter
  : BrowserRouter;

// Apply persisted font scale immediately (before first render)
applyFontScale(useFontScaleStore.getState().fontScale);

// Subscribe store → auto-apply + trigger re-render on changes
useFontScaleStore.subscribe((state) => {
  applyFontScale(state.fontScale);
  triggerFontScaleRerender();
});

function Root() {
  // Re-render this tree whenever font scale changes
  useFontScaleRerender();
  const fontScale = useFontScaleStore((s) => s.fontScale);

  // Recreate MUI theme with current scale (memoized on fontScale level)
  const theme = useMemo(() => createAppThemeScaled(), [fontScale]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Router>
        <App />
      </Router>
    </ThemeProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);

