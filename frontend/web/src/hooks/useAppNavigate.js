import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../api/ApiContext";

/**
 * Drop-in replacement for useNavigate that auto-prefixes /debug
 * when running in mock mode. Ensures navigation stays within
 * /debug/doctor/* routes instead of escaping to /doctor/*.
 *
 * Non-string args (e.g. -1 for back) pass through unchanged.
 */
export function useAppNavigate() {
  const navigate = useNavigate();
  const { isMock } = useApi();
  return useCallback((to, options) => {
    if (isMock && typeof to === "string" && to.startsWith("/doctor")) {
      navigate("/debug" + to, options);
    } else {
      navigate(to, options);
    }
  }, [navigate, isMock]);
}
