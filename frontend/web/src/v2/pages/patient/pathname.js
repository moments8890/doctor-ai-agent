/**
 * Pure helpers that translate a URL pathname into the currently-active
 * patient portal section or subpage. Mirrors the pattern used by
 * v2 DoctorPage (which parses location.pathname directly).
 *
 * These must stay side-effect free so they can be unit-tested without
 * a router context.
 */

const TABS = ["chat", "records", "tasks", "profile"];

/** /patient[/:tab[/:subpage]] → "chat" | "records" | "tasks" | "profile" (default "chat"). */
export function detectSection(pathname) {
  if (!pathname || pathname === "/patient" || pathname === "/patient/") return "chat";
  const parts = pathname.split("/").filter(Boolean); // ["patient", ...]
  const tab = parts[1];
  if (TABS.includes(tab)) return tab;
  return "chat";
}

/** /patient/records/:id → id (excluding "intake"). Returns null otherwise. */
export function detectRecordDetail(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[1] !== "records" || !parts[2] || parts[2] === "intake") return null;
  return parts[2];
}

/** /patient/tasks/:id → id. Returns null otherwise. */
export function detectTaskDetail(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[1] !== "tasks" || !parts[2]) return null;
  return parts[2];
}

/** /patient/profile/:sub → "about" | "privacy" | null. */
export function detectProfileSubpage(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  if (parts[1] !== "profile" || !parts[2]) return null;
  if (parts[2] === "about" || parts[2] === "privacy") return parts[2];
  return null;
}
