// Single source for the v2 app version. Used by doctor + patient about subpages.
// Set via Vite at build time (vite.config.js: define APP_VERSION) or fall back to literal.
export const APP_VERSION =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_APP_VERSION) || "1.0.0";

export const BUILD_HASH =
  (typeof import.meta !== "undefined" && import.meta.env?.VITE_BUILD_HASH) || null;
