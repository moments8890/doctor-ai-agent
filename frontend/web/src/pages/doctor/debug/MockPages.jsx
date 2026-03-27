/**
 * @route /debug/doctor-pages
 * Legacy entry point — redirects to /debug/doctor.
 * The actual mock rendering is handled by MockApiProvider + DoctorPage
 * mounted at /debug/doctor/* in App.jsx.
 */
import { Navigate } from "react-router-dom";
export default function MockPages() {
  return <Navigate to="/debug/doctor" replace />;
}
