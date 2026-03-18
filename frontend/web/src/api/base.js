// In mobile builds (Capacitor), set VITE_API_BASE_URL to the backend origin,
// e.g. https://your-server.com — relative /api/... paths don't resolve in WebView.
const _API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export function apiUrl(path) {
  return `${_API_BASE}${path}`;
}

export async function readError(response) {
  const text = await response.text();
  return text || `HTTP ${response.status}`;
}

let _webToken = "";

export function setWebToken(token) {
  _webToken = token || "";
}

/** Read token from module cache, falling back to Zustand's persisted localStorage entry.
 *  This handles the window between page load (store re-hydrated) and the App.jsx
 *  useEffect that calls setWebToken — during that gap _webToken is empty but the
 *  token already exists in localStorage. */
function _getToken() {
  if (_webToken) return _webToken;
  try {
    const raw = localStorage.getItem("doctor-session");
    if (raw) {
      const token = JSON.parse(raw)?.state?.accessToken;
      if (token) {
        _webToken = token; // warm the cache for subsequent calls
        return token;
      }
    }
  } catch {
    // ignore parse errors
  }
  return "";
}

/** Expose the resolved web token for domain modules that need raw fetch access. */
export function getWebToken() {
  return _getToken();
}

export async function request(url, options = {}) {
  const controller = new AbortController();
  const timeoutMs = options._timeout ?? 15000;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = { ...(options.headers || {}) };
    const token = _getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    if (typeof window !== "undefined" && window.__wxjs_environment === "miniprogram") {
      headers["X-Client-Channel"] = "miniapp";
    }
    const response = await fetch(apiUrl(url), { ...options, headers, signal: controller.signal });
    if (!response.ok) {
      const err = new Error(await readError(response));
      err.status = response.status;
      if (response.status === 401) { _authExpiredHandler?.(); }
      throw err;
    }
    return response.json();
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

let _adminToken = "";
let _adminAuthErrorHandler = null;

let _authExpiredHandler = null;
export function onAuthExpired(handler) { _authExpiredHandler = handler; }

export function setAdminToken(token) { _adminToken = token || ""; }
export function onAdminAuthError(handler) { _adminAuthErrorHandler = handler; }

export async function adminRequest(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (_adminToken) headers["X-Admin-Token"] = _adminToken;
  try {
    return await request(url, { ...options, headers });
  } catch (err) {
    if (err.status === 403 || err.status === 503) {
      _adminAuthErrorHandler?.();
    }
    throw err;
  }
}

let _debugToken = "";
let _debugAuthErrorHandler = null;

export function setDebugToken(token) { _debugToken = token || ""; }
export function onDebugAuthError(handler) { _debugAuthErrorHandler = handler; }

export async function debugRequest(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (_debugToken) headers["X-Debug-Token"] = _debugToken;
  try {
    return await request(url, { ...options, headers });
  } catch (err) {
    if (err.status === 403 || err.status === 503) {
      _debugAuthErrorHandler?.();
    }
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Patient portal request helper (uses X-Patient-Token header)
// ---------------------------------------------------------------------------

export async function patientRequest(url, patientToken, options = {}) {
  const headers = {
    ...(options.headers || {}),
    "X-Patient-Token": patientToken || "",
  };
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(apiUrl(url), { ...options, headers, signal: controller.signal });
    if (!response.ok) {
      const err = new Error(await readError(response));
      err.status = response.status;
      throw err;
    }
    return response.json();
  } catch (err) {
    if (err.name === "AbortError") throw new Error("Request timed out");
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}
