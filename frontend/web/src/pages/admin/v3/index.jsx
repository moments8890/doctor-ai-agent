// AdminPageV3 — entry point for the admin v3 surface (?v=3).
//
// Routing contract (URL params):
//   ?v=3                          → DoctorList (fallback)
//   ?v=3&doctor=<id>              → AdminDoctorDetailV3
//   ?v=3&section=ops/<sub>        → OpsPage (运营 module)
//     subs: invites | pilot | report | export
//
// Re-renders when the URL changes via `popstate` (DoctorList rows and the
// ops sidebar links both dispatch a synthetic popstate after pushState).
//
// TODO(v3): role auto-detection from backend. For v1 we read role from
// localStorage["adminRole"] (see devMode.js → getAdminRole) and default to
// "super" in dev. To probe the backend on first entry we'd hit
// /api/admin/cleanup/preview (super → 200, viewer → 403) and cache the
// result, but that adds a startup round-trip and an extra failure mode.
// Skipping for now — operators set the role explicitly via localStorage
// when handing the URL to a viewer.

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { onAdminAuthError, setAdminToken } from "../../../api";
import { setPageTitle } from "../../../lib/pageTitle";
import AdminShellV3 from "./AdminShellV3";
import AdminDoctorDetailV3 from "./doctorDetail/AdminDoctorDetailV3";
import DoctorList from "./doctorDetail/DoctorList";
import OpsPage from "./ops/OpsPage";
import OverviewPlaceholder from "./overview/OverviewPlaceholder";
import DashboardPage from "./overview/DashboardPage";
import AllPatientsPage from "./overview/AllPatientsPage";
import ChatCenterPage from "./overview/ChatCenterPage";
import AiActivityPage from "./overview/AiActivityPage";
import useDoctorDetail from "./hooks/useDoctorDetail";

const OPS_SUBS = {
  invites: "邀请码",
  pilot: "试点进度",
  report: "合作伙伴报表",
  export: "数据导出",
};

const OVERVIEW_SUBS = {
  dashboard: "仪表盘",
  patients:  "全体患者",
  chat:      "沟通中心",
  ai:        "知识 & AI",
};

function readRoute() {
  if (typeof window === "undefined") {
    return { doctorId: null, opsSub: null, overviewSub: null, sidebarSection: "doctors" };
  }
  const params = new URLSearchParams(window.location.search);
  const doctorId = params.get("doctor");
  const sectionRaw = params.get("section") || "";
  let opsSub = null;
  let overviewSub = null;
  let sidebarSection = "doctors";
  if (sectionRaw.startsWith("ops/")) {
    const sub = sectionRaw.slice(4);
    opsSub = sub in OPS_SUBS ? sub : "invites";
    sidebarSection = opsSub;
  } else if (sectionRaw.startsWith("overview/")) {
    const sub = sectionRaw.slice(9);
    overviewSub = sub in OVERVIEW_SUBS ? sub : "dashboard";
    // Map overview subsection → sidebar item key (matches AdminSidebar NAV_GROUPS).
    sidebarSection = overviewSub;
  }
  return { doctorId, opsSub, overviewSub, sidebarSection };
}

function useUrlRoute() {
  const [route, setRoute] = useState(() => readRoute());
  useEffect(() => {
    function onPop() {
      setRoute(readRoute());
    }
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return route;
}

// Renders the doctor detail surface and forwards the resolved doctor name
// into the topbar breadcrumb (calls useDoctorDetail at this level so the
// breadcrumb has access to `doctor.name` without prop drilling).
function DoctorDetailWithBreadcrumb({ doctorId }) {
  const { doctor } = useDoctorDetail(doctorId);
  const breadcrumb = [
    { label: "医生" },
    { label: doctor?.name || doctorId, here: true },
  ];
  return (
    <AdminShellV3 section="doctors" breadcrumb={breadcrumb}>
      <AdminDoctorDetailV3 doctorId={doctorId} />
    </AdminShellV3>
  );
}

export default function AdminPageV3() {
  const { doctorId, opsSub, overviewSub, sidebarSection } = useUrlRoute();
  const navigate = useNavigate();

  useEffect(() => {
    let label = "运营总览";
    if (opsSub) label = OPS_SUBS[opsSub] || "运营总览";
    else if (overviewSub) label = OVERVIEW_SUBS[overviewSub] || "运营总览";
    else if (doctorId) label = "医生详情";
    else label = "医生列表";
    setPageTitle("admin", label);
  }, [doctorId, opsSub, overviewSub]);

  // V3 owns its admin lockout handler. AdminPage's legacy wiring is bypassed
  // by the early-return at the top of AdminPage.jsx, so without this hook a
  // 403/503 would leave _adminAuthErrorHandler unset and a 401 would fall
  // through to v2/App.jsx's onAuthExpired (which sends doctors to /login).
  useEffect(() => {
    onAdminAuthError(() => {
      localStorage.removeItem("adminToken");
      setAdminToken("");
      navigate("/admin/login");
    });
    return () => onAdminAuthError(null);
  }, [navigate]);

  if (opsSub) {
    const breadcrumb = [
      { label: "运营" },
      { label: OPS_SUBS[opsSub], here: true },
    ];
    return (
      <AdminShellV3 section={sidebarSection} breadcrumb={breadcrumb}>
        <OpsPage subsection={opsSub} />
      </AdminShellV3>
    );
  }

  if (overviewSub) {
    const breadcrumb = [
      { label: "概览" },
      { label: OVERVIEW_SUBS[overviewSub], here: true },
    ];
    return (
      <AdminShellV3 section={sidebarSection} breadcrumb={breadcrumb}>
        {overviewSub === "dashboard" ? (
          <DashboardPage />
        ) : overviewSub === "patients" ? (
          <AllPatientsPage />
        ) : overviewSub === "chat" ? (
          <ChatCenterPage />
        ) : overviewSub === "ai" ? (
          <AiActivityPage />
        ) : (
          <OverviewPlaceholder sub={overviewSub} />
        )}
      </AdminShellV3>
    );
  }

  if (doctorId) {
    return <DoctorDetailWithBreadcrumb doctorId={doctorId} />;
  }

  return (
    <AdminShellV3
      section="doctors"
      breadcrumb={[{ label: "医生" }, { label: "选择医生", here: true }]}
    >
      <DoctorList />
    </AdminShellV3>
  );
}
