import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import DoctorPage from "./pages/DoctorPage";
import AdminPage from "./pages/AdminPage";
import AdminLoginPage from "./pages/AdminLoginPage";
import DebugPage from "./pages/DebugPage";
import LoginPage from "./pages/LoginPage";
import PatientPage from "./pages/PatientPage";
import PrivacyPage from "./pages/PrivacyPage";
import ComponentShowcasePage from "./pages/ComponentShowcasePage";
import { useDoctorStore } from "./store/doctorStore";
import { setWebToken, onAuthExpired } from "./api";
import { isMiniApp } from "./utils/env";

import Box from "@mui/material/Box";

const DEV_MODE = import.meta.env.DEV; // true in `vite dev`, false in `vite build`

/**
 * On wide screens (>520px), constrains the app to a phone-shaped container
 * with 9:19.5 aspect ratio. Uses CSS min() to pick whichever dimension
 * is the binding constraint — width or height — so it always fits.
 * On actual mobile (<520px), renders full-screen.
 */
function MobileFrame({ children }) {
  // Aspect ratio: 9 / 19.5 ≈ 0.4615
  // Height from width: h = w / 0.4615 = w * 2.167
  // Width from height: w = h * 0.4615
  return (
    <Box sx={{
      width: "100vw", height: "100vh", display: "flex",
      justifyContent: "center", alignItems: "center",
      bgcolor: "transparent",
      "@media (min-width: 520px)": { bgcolor: "#e8e8e8" },
    }}>
      <Box sx={{
        width: "100%", height: "100%",
        overflow: "hidden",
        position: "relative",
        "@media (min-width: 520px)": {
          // Pick the smaller of: height-driven width vs width-driven width
          width: "min(calc(95vh * 9 / 19.5), 90vw)",
          // Pick the smaller of: width-driven height vs height-driven height
          height: "min(calc(90vw * 19.5 / 9), 95vh)",
          maxWidth: 480,
          borderRadius: "16px",
          boxShadow: "0 4px 24px rgba(0,0,0,0.12)",
          // Creates a new containing block for position:fixed children
          // so they stay inside the frame instead of viewport
          transform: "translateZ(0)",
        },
      }}>
        {children}
      </Box>
    </Box>
  );
}
const DEV_DOCTOR_ID = import.meta.env.VITE_DEV_DOCTOR_ID || "test_doctor";

function RequireAuth({ children }) {
  const { accessToken } = useDoctorStore();
  if (DEV_MODE) return children; // Skip auth gate in dev
  if (!accessToken) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const { accessToken, doctorId, setAuth } = useDoctorStore();

  // Dev mode: auto-set doctor identity so login is never required
  useState(() => {
    if (DEV_MODE && !doctorId) {
      setAuth(DEV_DOCTOR_ID, DEV_DOCTOR_ID, "dev-token");
    }
  });

  // Absorb token handed off from WeChat Mini Program web-view via URL params.
  useState(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const did = params.get("doctor_id");
    const name = params.get("name");
    if (token && did) {
      setAuth(did, name || did, token);
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

  // Handle 401 token expiry — Mini App shows message, web redirects to login
  useEffect(() => {
    onAuthExpired(() => {
      if (isMiniApp()) {
        alert("会话已过期，请关闭后重新打开小程序");
      } else {
        useDoctorStore.getState().clearAuth();
        window.location.href = "/login";
      }
    });
  }, []);

  return (
    <Routes>
      {/* Mobile-framed routes (doctor, patient, login) */}
      <Route path="/privacy" element={<MobileFrame><PrivacyPage /></MobileFrame>} />
      <Route path="/login" element={<MobileFrame><LoginPage /></MobileFrame>} />
      <Route path="/" element={<Navigate to="/doctor" replace />} />
      <Route path="/doctor" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/patients/:patientId" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/review/:recordId" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section/:subpage" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/doctor/:section/:subpage/:subId" element={<MobileFrame><RequireAuth><DoctorPage /></RequireAuth></MobileFrame>} />
      <Route path="/patient" element={<MobileFrame><PatientPage /></MobileFrame>} />
      <Route path="/patient/:tab" element={<MobileFrame><PatientPage /></MobileFrame>} />
      <Route path="/patient/:tab/:subpage" element={<MobileFrame><PatientPage /></MobileFrame>} />
      {/* Admin — full desktop layout, no MobileFrame */}
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/admin/:section" element={<AdminPage />} />
      {/* Debug — full desktop layout */}
      <Route path="/debug" element={<DebugPage />} />
      <Route path="/debug/:section" element={<DebugPage />} />
      {/* Component showcase — no frame, scrollable */}
      <Route path="/debug/components" element={<ComponentShowcasePage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
