import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import ChatPage from "./pages/ChatPage";
import ManagePage from "./pages/ManagePage";
import AdminPage from "./pages/AdminPage";
import AdminLoginPage from "./pages/AdminLoginPage";
import DebugPage from "./pages/DebugPage";
import LoginPage from "./pages/LoginPage";
import { useDoctorStore } from "./store/doctorStore";
import { setWebToken } from "./api";

function RequireAuth({ children }) {
  const { accessToken } = useDoctorStore();
  if (!accessToken) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const { accessToken } = useDoctorStore();

  // Restore token into api module on page reload (Zustand persist re-hydrates store
  // but the module-level _webToken variable resets on each page load).
  useEffect(() => {
    if (accessToken) setWebToken(accessToken);
  }, [accessToken]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><ChatPage /></RequireAuth>} />
      <Route path="/manage" element={<RequireAuth><ManagePage /></RequireAuth>} />
      <Route path="/admin/login" element={<AdminLoginPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="/admin/:section" element={<AdminPage />} />
      <Route path="/debug" element={<DebugPage />} />
      <Route path="/debug/:section" element={<DebugPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
