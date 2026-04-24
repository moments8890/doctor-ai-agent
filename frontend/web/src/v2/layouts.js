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
 * No keyboard-related height math — textarea relies on the browser's
 * default behavior when the soft keyboard opens.
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
