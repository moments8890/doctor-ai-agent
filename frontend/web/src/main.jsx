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

// Default to MemoryRouter while we're in beta — paths never appear in any
// address bar and deep-linking via URL is impossible across web, miniapp,
// and Capacitor builds. To get URLs back (E2E tests, sharable dev links),
// set VITE_ROUTER_MODE=browser.
const Router = import.meta.env.VITE_ROUTER_MODE === "browser" ? BrowserRouter : MemoryRouter;

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

