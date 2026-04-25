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
import AdminShellV3 from "./AdminShellV3";
import AdminDoctorDetailV3 from "./doctorDetail/AdminDoctorDetailV3";
import DoctorList from "./doctorDetail/DoctorList";
import OpsPage from "./ops/OpsPage";
import useDoctorDetail from "./hooks/useDoctorDetail";

const OPS_SUBS = {
  invites: "邀请码",
  pilot: "试点进度",
  report: "合作伙伴报表",
  export: "数据导出",
};

function readRoute() {
  if (typeof window === "undefined") {
    return { doctorId: null, opsSub: null, sidebarSection: "doctors" };
  }
  const params = new URLSearchParams(window.location.search);
  const doctorId = params.get("doctor");
  const sectionRaw = params.get("section") || "";
  let opsSub = null;
  let sidebarSection = "doctors";
  if (sectionRaw.startsWith("ops/")) {
    const sub = sectionRaw.slice(4);
    opsSub = sub in OPS_SUBS ? sub : "invites";
    // Map ops subsection → sidebar item key (matches AdminSidebar NAV_GROUPS).
    sidebarSection = opsSub;
  }
  return { doctorId, opsSub, sidebarSection };
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
  const { doctorId, opsSub, sidebarSection } = useUrlRoute();

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
