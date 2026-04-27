/** @route /admin, /admin/:section
 *
 * Thin shim that mounts the V3 admin surface and threads the admin token
 * into api.js's module cache during render — must happen before any V3
 * child component's useEffect fires its first /api/admin/* call.
 *
 * Pre-2026-04-27 this file hosted a parallel GitHub-Dark v1 admin
 * (`?v=1` fallback) with a raw-DB browser, cleanup tool, and its own
 * sidebar + lockout flow. dbgate now covers the raw-data view, so v1
 * was removed in its entirety. This file is what's left because
 * v2/App.jsx routes /admin/* to it via React.lazy() — keeping the
 * import contract stable.
 *
 * Lockout handler (403/503 → /admin/login) is registered inside
 * AdminPageV3 itself; we don't need to duplicate it here.
 */

import { Navigate, useLocation } from "react-router-dom";
import { setAdminToken } from "../../api";
import AdminPageV3 from "./v3";

const ADMIN_TOKEN_KEY = "adminToken";
const DEV_MODE = import.meta.env.DEV;

// In dev mode, set token synchronously before any component renders.
if (DEV_MODE) setAdminToken("dev");

export default function AdminPage() {
  const location = useLocation();

  // Populate the api.js admin token cache synchronously on every render so
  // V3 children (which fire API calls in their own mount useEffects, before
  // any parent useEffect) see X-Admin-Token from the very first request.
  // If no token is stored, gate the entire admin surface behind /admin/login —
  // preserves the requested URL via location.state.next so the login page
  // sends the user back here on success.
  if (!DEV_MODE && typeof window !== "undefined") {
    const stored = localStorage.getItem(ADMIN_TOKEN_KEY) || "";
    if (!stored) {
      return (
        <Navigate
          to="/admin/login"
          replace
          state={{ next: location.pathname + location.search + location.hash }}
        />
      );
    }
    setAdminToken(stored);
  }

  return <AdminPageV3 />;
}
