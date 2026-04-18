// Bridge between the React SPA (running inside WeChat miniapp web-view)
// and native miniapp pages. In a regular browser, these helpers are no-ops.

export function isInMiniapp() {
  return typeof window !== "undefined"
    && window.__wxjs_environment === "miniprogram";
}

/** True when inline voice recording is available (requires miniapp bridge). */
export function isVoiceSupported() {
  return isInMiniapp();
}
