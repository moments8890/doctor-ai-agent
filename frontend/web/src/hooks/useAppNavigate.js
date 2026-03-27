import { useCallback, useContext } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../api/ApiContext";
import { PatientApiContext } from "../api/PatientApiContext";

/**
 * Drop-in replacement for useNavigate that auto-prefixes /debug
 * when running in mock mode. Ensures navigation stays within
 * /debug/* routes instead of escaping to real routes.
 *
 * Works for both doctor (/doctor/*) and patient (/patient/*) apps.
 * Non-string args (e.g. -1 for back) pass through unchanged.
 */
export function useAppNavigate() {
  const navigate = useNavigate();
  // Check both doctor and patient contexts — only one will be active
  let isMock = false;
  try { isMock = useApi()?.isMock; } catch { /* not in doctor context */ }
  const patientCtx = useContext(PatientApiContext);
  if (patientCtx?.isMock) isMock = true;

  return useCallback((to, options) => {
    if (isMock && typeof to === "string" && (to.startsWith("/doctor") || to.startsWith("/patient"))) {
      navigate("/debug" + to, options);
    } else {
      navigate(to, options);
    }
  }, [navigate, isMock]);
}
