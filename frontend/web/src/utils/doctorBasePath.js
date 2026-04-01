/**
 * Returns the doctor app base path: "/doctor" or "/mock/doctor".
 * Used by all navigate() calls to stay within the correct prefix.
 */
export function getDoctorBasePath() {
  return window.location.pathname.startsWith("/mock/doctor") ? "/mock/doctor" : "/doctor";
}

/**
 * Build a doctor-relative path: dp("patients") → "/doctor/patients" or "/mock/doctor/patients"
 */
export function dp(suffix) {
  const base = getDoctorBasePath();
  return suffix ? `${base}/${suffix}` : base;
}
