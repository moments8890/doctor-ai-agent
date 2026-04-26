/**
 * pageTitle — set document.title with [env][role] prefix so users can tell
 * dev vs prod tabs apart and identify which surface (wiki / admin / main app)
 * they're looking at.
 *
 * env detection:
 *   - localhost / 127.0.0.1 / :5173 / :5174 → "dev"
 *   - *.doctoragentai.cn → "内测版"
 *   - anything else → no env prefix (test harness, file://, unknown host)
 *
 * role: "wiki" | "admin" | null (main app — env prefix only)
 */
export function getEnvLabel() {
  if (typeof window === "undefined") return "";
  const host = window.location.hostname;
  const port = window.location.port;
  if (host === "localhost" || host === "127.0.0.1" || port === "5173" || port === "5174") {
    return "dev";
  }
  if (host.endsWith(".doctoragentai.cn")) {
    return "内测版";
  }
  return "";
}

export function buildTitle(role, label) {
  const env = getEnvLabel();
  const prefix = [env, role].filter(Boolean).map((s) => `[${s}]`).join("");
  // For internal pages (role set), the prefix is the identifier — don't repeat
  // the brand label in the tab. Empty / falsy labels collapse cleanly.
  if (!label) return prefix || "";
  return prefix ? `${prefix} ${label}` : label;
}

export function setPageTitle(role, label) {
  if (typeof document === "undefined") return;
  document.title = buildTitle(role, label);
}
