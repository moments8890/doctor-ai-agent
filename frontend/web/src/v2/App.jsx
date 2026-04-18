/**
 * v2 App shell — antd-mobile ConfigProvider + SafeArea.
 * Activated via VITE_USE_V2=true.
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ConfigProvider } from "antd-mobile";
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

  const { accessToken, doctorId, setAuth } = useDoctorStore();

  // Init antd-mobile theme on mount
  useEffect(() => {
    const fontScale = useFontScaleStore.getState().fontScale;
    initTheme(fontScale || "large");
  }, []);

  // Apply font scale whenever it changes
  useEffect(() => {
    return useFontScaleStore.subscribe((state) => {
      applyFontScale(state.fontScale || "large");
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
        <MobileFrame>
          <Routes>
            <Route
              path="/login"
              element={<PlaceholderPage name="LoginPage" />}
            />
            <Route path="/" element={<Navigate to="/doctor" replace />} />
            <Route
              path="/doctor/*"
              element={
                <RequireAuth>
                  <ApiProvider>
                    <PlaceholderPage name="DoctorPage" />
                  </ApiProvider>
                </RequireAuth>
              }
            />
            <Route
              path="/patient/*"
              element={
                <PatientApiProvider>
                  <PlaceholderPage name="PatientPage" />
                </PatientApiProvider>
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
