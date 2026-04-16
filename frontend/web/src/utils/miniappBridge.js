// Bridge between the React SPA (running inside WeChat miniapp web-view)
// and native miniapp pages. In a regular browser, these helpers are no-ops.

// WeChat injects window.__wxjs_environment === "miniprogram" inside miniapp
// web-view; this matches the existing convention used by utils/env.js.
export function isInMiniapp() {
  return typeof window !== "undefined"
    && window.__wxjs_environment === "miniprogram";
}

export function openAddRuleVoice({ onStaleVersion } = {}) {
  if (!isInMiniapp()) return;
  const nav = window.wx && window.wx.miniProgram && window.wx.miniProgram.navigateTo;
  if (typeof nav !== "function") return;
  nav({
    url: "/pages/add-rule/add-rule",
    fail: () => { if (onStaleVersion) onStaleVersion(); },
  });
}
