/**
 * v2 App shell — antd-mobile ConfigProvider + SafeArea.
 * Activated via VITE_USE_V2=true.
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { decideColdStartSeed } from "./coldStartSeed";
import { ConfigProvider, unstableSetRender } from "antd-mobile";

// React 19 compatibility — antd-mobile v5 uses ReactDOM.render internally
// for imperative APIs (Dialog.confirm, Toast.show). This shim uses createRoot.
unstableSetRender((node, container) => {
  const root = createRoot(container);
  root.render(node);
  return () => root.unmount();
});
import { QueryClientProvider } from "@tanstack/react-query";
import {
  onAuthExpired,
  setWebToken,
  fetchDraftSummary,
  getTasks,
} from "../api";
import { queryClient } from "../lib/queryClient";
import { QK } from "../lib/queryKeys";
import { ApiProvider } from "../api/ApiContext";
import { PatientApiProvider } from "../api/PatientApiContext";
import { useDoctorStore } from "../store/doctorStore";
import {
  syncFontScaleFromServer,
  saveFontScaleToServer,
  useFontScaleStore,
} from "../store/fontScaleStore";
import { isMiniApp } from "../utils/env";
import { useKeyboard } from "./keyboard";
import { initTheme, applyFontScale } from "./theme";

// Lazy-load admin pages
const AdminLoginPage = lazy(() => import("../pages/admin/AdminLoginPage"));
const AdminPage = lazy(() => import("../pages/admin/AdminPage"));

import LoginPage from "./pages/login/LoginPage";
import DoctorPage from "./pages/doctor/DoctorPage";
import OnboardingWizard from "./pages/doctor/OnboardingWizard";
import PatientPage from "./pages/patient/PatientPage";
import PrivacyPage from "./pages/PrivacyPage";
import KeyboardDebugHUD from "./KeyboardDebugHUD";

const DEV_MODE = import.meta.env.DEV;
const DEV_DOCTOR_ID = import.meta.env.VITE_DEV_DOCTOR_ID || "test_doctor";
const DEV_DOCTOR_NAME = import.meta.env.VITE_DEV_DOCTOR_NAME || "";

const SYNTHETIC_TOKENS = ["dev-token", "mock-token"];
const SYNTHETIC_IDS = [DEV_DOCTOR_ID, "mock_doctor"];

function isSyntheticSession(id, token) {
  return (
    !id ||
    !token ||
    SYNTHETIC_TOKENS.includes(token) ||
    SYNTHETIC_IDS.includes(id)
  );
}

function applySyntheticDevSession(setAuth) {
  setAuth(DEV_DOCTOR_ID, DEV_DOCTOR_NAME, "dev-token");
}

function RequireAuth({ children }) {
  const { accessToken } = useDoctorStore();
  if (DEV_MODE) return children;
  if (!accessToken) return <Navigate to="/login" replace />;
  return children;
}

/**
 * Pure-CSS mobile frame — constrains to phone shape on wide screens.
 * Uses plain divs (no MUI) so it works without MUI ThemeProvider.
 */
function MobileFrame({ children }) {
  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        backgroundColor: "transparent",
      }}
      className="v2-mobile-outer"
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          overflow: "hidden",
          position: "relative",
        }}
        className="v2-mobile-inner"
      >
        {children}
      </div>
    </div>
  );
}

// Placeholder for mobile routes not yet ported to v2
function PlaceholderPage({ name }) {
  return (
    <div style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      {name} — v2 coming soon
    </div>
  );
}

export default function App() {
  useKeyboard();
  const navigate = useNavigate();

  const { accessToken, doctorId, setAuth } = useDoctorStore();

  // Init antd-mobile theme on mount
  useEffect(() => {
    const fontScale = useFontScaleStore.getState().fontScale;
    initTheme(fontScale || "standard");
  }, []);

  // Single-tab IA: seed a synthetic /doctor/my-ai history entry behind any
  // cold-start deep-link to a doctor subpage so the back button unwinds to
  // home instead of exiting the app (WeChat/iOS push entry case).
  useEffect(() => {
    const decision = decideColdStartSeed({
      pathname: window.location.pathname,
      search: window.location.search,
      hash: window.location.hash,
      historyLength: window.history.length,
    });
    if (decision.kind === "seed") {
      navigate(decision.homePath, { replace: true });
      navigate(decision.target, { replace: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Apply font scale whenever it changes
  useEffect(() => {
    return useFontScaleStore.subscribe((state) => {
      applyFontScale(state.fontScale || "standard");
    });
  }, []);

  // Dev mode: restore real login session if current session is synthetic
  function restoreRealSession() {
    const state = useDoctorStore.getState();
    if (!isSyntheticSession(state.doctorId, state.accessToken)) return;

    const savedId = localStorage.getItem("unified_auth_doctor_id");
    const savedToken = localStorage.getItem("unified_auth_token");
    const savedName = localStorage.getItem("unified_auth_name");
    if (savedId && savedToken && !isSyntheticSession(savedId, savedToken)) {
      state.setAuth(savedId, savedName || savedId, savedToken);
    } else {
      applySyntheticDevSession(state.setAuth);
    }
  }

  useEffect(() => {
    if (!DEV_MODE) return;
    const unsub = useDoctorStore.persist.onFinishHydration(restoreRealSession);
    if (useDoctorStore.persist.hasHydrated()) restoreRealSession();
    return unsub;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync fallback for first render (before hydration)
  useState(() => {
    if (DEV_MODE && !doctorId) {
      const savedId = localStorage.getItem("unified_auth_doctor_id");
      const savedToken = localStorage.getItem("unified_auth_token");
      const savedName = localStorage.getItem("unified_auth_name");
      if (savedId && savedToken && !isSyntheticSession(savedId, savedToken)) {
        setAuth(savedId, savedName || savedId, savedToken);
      } else {
        applySyntheticDevSession(setAuth);
      }
    }
  });

  // Absorb token from WeChat Mini Program web-view URL params
  useState(() => {
    // Skip if the user just explicitly signed out — the WeChat miniprogram
    // WebView may reload with ?token= in the URL on refresh; without this
    // guard the absorber would silently re-authenticate the user we just
    // signed out. Cleared on next successful login (LoginPage).
    if (localStorage.getItem("explicit_signout") === "1") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const did = params.get("doctor_id");
    const name = params.get("name");
    if (token && did) {
      let canonicalDid = did;
      let canonicalName = name;
      try {
        const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
        const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
        const payload = JSON.parse(atob(padded));
        if (typeof payload.doctor_id === "string" && payload.doctor_id)
          canonicalDid = payload.doctor_id;
        if (typeof payload.name === "string" && payload.name)
          canonicalName = payload.name;
      } catch {
        /* ignore malformed token */
      }
      setAuth(canonicalDid, canonicalName || canonicalDid, token);
      setWebToken(token);
      const url = new URL(window.location.href);
      ["token", "doctor_id", "name"].forEach((k) => url.searchParams.delete(k));
      window.history.replaceState({}, "", url.toString());
    }
  });

  // Restore token into api module on page reload
  useEffect(() => {
    if (accessToken) setWebToken(accessToken);
  }, [accessToken]);

  // Boot-time prefetch of badge-critical data after auth is established
  useEffect(() => {
    if (!accessToken || !doctorId) return;
    queryClient.prefetchQuery({
      queryKey: QK.draftSummary(doctorId),
      queryFn: () => fetchDraftSummary(doctorId),
      staleTime: 30_000,
    });
    queryClient.prefetchQuery({
      queryKey: QK.tasks(doctorId, "pending"),
      queryFn: () => getTasks(doctorId, "pending"),
      staleTime: 60_000,
    });
    syncFontScaleFromServer(doctorId);
  }, [accessToken, doctorId]);

  // Save font scale to server whenever it changes
  useEffect(() => {
    if (!doctorId) return;
    return useFontScaleStore.subscribe(() => saveFontScaleToServer(doctorId));
  }, [doctorId]);

  // Handle 401 token expiry
  useEffect(() => {
    onAuthExpired(() => {
      if (isMiniApp()) {
        useDoctorStore.getState().clearAuth();
        alert("会话已过期，请关闭后重新打开小程序");
        // eslint-disable-next-line no-undef
        wx.miniProgram?.navigateBack?.();
      } else {
        useDoctorStore.getState().clearAuth();
        window.location.href = "/login";
      }
    });
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider>
        {/* <KeyboardDebugHUD /> — re-enable to diagnose keyboard issues */}
        <MobileFrame>
          <Routes>
            <Route
              path="/login"
              element={<LoginPage />}
            />
            <Route path="/" element={<Navigate to="/doctor" replace />} />
            <Route
              path="/doctor/onboarding"
              element={
                <MobileFrame>
                  <RequireAuth>
                    <ApiProvider>
                      <OnboardingWizard />
                    </ApiProvider>
                  </RequireAuth>
                </MobileFrame>
              }
            />
            <Route
              path="/doctor/*"
              element={
                <MobileFrame>
                  <RequireAuth>
                    <ApiProvider>
                      <DoctorPage />
                    </ApiProvider>
                  </RequireAuth>
                </MobileFrame>
              }
            />
            {["", "/:tab", "/:tab/:subpage"].map((suffix) => (
              <Route
                key={`/patient${suffix}`}
                path={`/patient${suffix}`}
                element={
                  <MobileFrame>
                    <PatientApiProvider>
                      <PatientPage />
                    </PatientApiProvider>
                  </MobileFrame>
                }
              />
            ))}
            <Route
              path="/privacy"
              element={
                <MobileFrame>
                  <PrivacyPage />
                </MobileFrame>
              }
            />
            {/* Admin — full desktop layout, no MobileFrame */}
            <Route
              path="/admin/login"
              element={
                <Suspense fallback={null}>
                  <AdminLoginPage />
                </Suspense>
              }
            />
            <Route
              path="/admin/*"
              element={
                <Suspense fallback={null}>
                  <AdminPage />
                </Suspense>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </MobileFrame>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
