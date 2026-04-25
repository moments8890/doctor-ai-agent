// devMode — admin v3 dev-mode toggle + role helpers.
//
// The admin v3 surface has two roles:
//   - "super":  full access (sees 系统 nav-group, may toggle raw_db_view)
//   - "viewer": read-only (no 系统 group, no dev toggle)
//
// Dev-mode (`adminDevMode === "1"`) gates the 系统 nav-group on top of
// role. Even a super user only sees 系统 when dev-mode is on. Viewers
// never see it regardless. This mirrors the backend gate in
// `src/channels/web/doctor_dashboard/deps.py` (require_admin_super).
//
// Storage:
//   localStorage["adminRole"]    "super" | "viewer"   (set on login / detection)
//   localStorage["adminDevMode"] "1" when dev-mode is enabled
//
// Listeners subscribe to a custom DOM event `admin-devmode-changed` that
// fires whenever toggleDevMode() is called. The hooks below re-read state
// when the event fires so consumers re-render without prop drilling.

import { useEffect, useState } from "react";

const ROLE_KEY = "adminRole";
const DEV_KEY = "adminDevMode";
const EVENT_NAME = "admin-devmode-changed";

function readStorage(key) {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  if (typeof window === "undefined") return;
  try {
    if (value == null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* ignore quota / SecurityError */
  }
}

export function getAdminRole() {
  const stored = readStorage(ROLE_KEY);
  if (stored === "super" || stored === "viewer") return stored;
  // Default: super in dev (so the local dashboard works without a token
  // round-trip), unknown otherwise (caller may probe the backend).
  if (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.DEV) {
    return "super";
  }
  return "unknown";
}

export function setAdminRole(role) {
  if (role !== "super" && role !== "viewer") {
    writeStorage(ROLE_KEY, null);
  } else {
    writeStorage(ROLE_KEY, role);
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(EVENT_NAME));
  }
}

export function isDevMode() {
  if (getAdminRole() !== "super") return false;
  return readStorage(DEV_KEY) === "1";
}

export function toggleDevMode() {
  const next = isDevMode() ? null : "1";
  writeStorage(DEV_KEY, next);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(EVENT_NAME));
  }
}

function useAdminEvent(read) {
  const [value, setValue] = useState(read);
  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const handler = () => setValue(read());
    window.addEventListener(EVENT_NAME, handler);
    // storage events fire across tabs — keep them in sync too.
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener(EVENT_NAME, handler);
      window.removeEventListener("storage", handler);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return value;
}

export function useAdminRole() {
  return useAdminEvent(getAdminRole);
}

export function useDevMode() {
  return useAdminEvent(isDevMode);
}
