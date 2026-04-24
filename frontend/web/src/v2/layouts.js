/**
 * Shared layout style constants for v2 pages.
 *
 * Usage:
 *   import { pageContainer, navBarStyle, scrollable, bottomBar } from "../../layouts";
 *   <div style={pageContainer}>
 *     <NavBar style={navBarStyle}>Title</NavBar>
 *     <div style={scrollable}>{children}</div>
 *   </div>
 */
import { APP } from "./theme";

/**
 * Standard full-height flex-column page wrapper.
 *
 * Page height is NOT shrunk when the keyboard opens. The browser handles
 * keyboard avoidance via native scroll-into-view for the focused input, and
 * the home-bar inset collapses via --safe-bottom (see useKeyboard).
 * Attempts to shrink via calc(100% - --keyboard-height) or var(--app-height)
 * double-counted on WKWebView — don't bring them back.
 */
export const pageContainer = {
  display: "flex",
  flexDirection: "column",
  height: "100%",
  backgroundColor: APP.surfaceAlt,
  overflow: "hidden",
};

/** Standard NavBar style (44px, bottom border, white bg). */
export const navBarStyle = {
  "--height": "44px",
  "--border-bottom": `0.5px solid ${APP.border}`,
  backgroundColor: APP.surface,
  flexShrink: 0,
};

/** Flex-1 scrollable content area. */
export const scrollable = {
  flex: 1,
  overflowY: "auto",
  WebkitOverflowScrolling: "touch",
};

/** Sticky bottom action bar with safe-area padding. */
export const bottomBar = {
  padding: "12px 16px",
  paddingBottom: "calc(12px + env(safe-area-inset-bottom, 0px))",
  backgroundColor: APP.surface,
  borderTop: `0.5px solid ${APP.border}`,
  flexShrink: 0,
};

/** Common flex utilities. */
export const flex = {
  center: { display: "flex", alignItems: "center", justifyContent: "center" },
  between: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  column: { display: "flex", flexDirection: "column" },
  row: (gap) => ({ display: "flex", alignItems: "center", gap }),
};
