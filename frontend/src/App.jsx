import { Navigate, Route, Routes } from "react-router-dom";
import ChatPage from "./pages/ChatPage";
import ManagePage from "./pages/ManagePage";
import AdminPage from "./pages/AdminPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ChatPage />} />
      <Route path="/manage" element={<ManagePage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
