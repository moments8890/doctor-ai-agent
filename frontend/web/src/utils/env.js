/** Always true — this is a mobile-only app. Use instead of useMediaQuery checks. */
export const isMobile = () => true;

/** WeChat miniprogram specifically — for wx SDK, auth, miniprogram navigation. */
export const isMiniApp = () =>
  window.__wxjs_environment === "miniprogram" ||
  (import.meta.env.DEV && localStorage.getItem("debug_miniapp") === "1");
