import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import DoctorPage from "./pages/DoctorPage";
import AdminPage from "./pages/AdminPage";
import AdminLoginPage from "./pages/AdminLoginPage";
import DebugPage from "./pages/DebugPage";
import LoginPage from "./pages/LoginPage";
import PatientPage from "./pages/PatientPage";
import { useDoctorStore } from "./store/doctorStore";
import { setWebToken } from "./api";

const DEV_MODE = import.meta.env.DEV; // true in `vite dev`, false in `vite build`
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
  // Runs synchronously in useState initializer so auth is set before RequireAuth
  // evaluates on the first render.
  useState(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const doctorId = params.get("doctor_id");
    const name = params.get("name");
    if (token && doctorId) {
      setAuth(doctorId, name || doctorId, token);
      setWebToken(token);
      // Strip sensitive params from the URL without triggering a navigation
      const url = new URL(window.location.href);
      ["token", "doctor_id", "name"].forEach((k) => url.searchParams.delete(k));
      window.history.replaceState({}, "", url.toString());
    }
  });

  // Restore token into api module on page reload (Zustand persist re-hydrates store
  // but the module-level _webToken variable resets on each page load).
  useEffect(() => {
    if (accessToken) setWebToken(accessToken);
  }, [accessToken]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/doctor" replace />} />
      <Route path="/manage" element={<Navigate to="/doctor" replace />} />
      <Route path="/doctor" element={<RequireAuth><DoctorPage /></RequireAuth>} />
      <Route path="/doctor/patients/:patientId" element={<RequireAuth><DoctorPage /></RequireAuth>} />
      <Route path="/doctor/:section" element={<RequireAuth><DoctorPage /></RequireAuth>} />
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/admin/:section" element={<AdminPage />} />
      <Route path="/debug" element={<DebugPage />} />
      <Route path="/debug/:section" element={<DebugPage />} />
      <Route path="/patient" element={<PatientPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
