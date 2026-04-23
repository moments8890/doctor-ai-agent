/**
 * @route /doctor/*
 *
 * v2 DoctorPage shell — antd-mobile TabBar + NavBar.
 * No MUI, no framer-motion, no complex subpage logic.
 * Placeholder content areas; real subpages wired in later tasks.
 *
 * InterviewPage overlay: rendered when path is /doctor/patients/new
 */
import { useState, useCallback, useRef, useMemo } from "react";
import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { usePageStack } from "../../usePageStack";
import { NavBar, SafeArea, TabBar, Button } from "antd-mobile";
import { usePatients } from "../../../lib/doctorQueries";
import InterviewPage from "./InterviewPage";
import MyAIPage from "./MyAIPage";
import PatientsPage from "./PatientsPage";
import PatientDetail from "./PatientDetail";
import PatientChatPage from "./PatientChatPage";
import ReviewQueuePage from "./ReviewQueuePage";
import ReviewPage from "./ReviewPage";
import SettingsPage from "./SettingsPage";
import PersonaSubpage from "./settings/PersonaSubpage";
import KnowledgeSubpage from "./settings/KnowledgeSubpage";
import AddKnowledgeSubpage from "./settings/AddKnowledgeSubpage";
import KnowledgeDetailSubpage from "./settings/KnowledgeDetailSubpage";
import SettingsListSubpage from "./settings/SettingsListSubpage";
import AboutSubpage from "./settings/AboutSubpage";
import TeachByExampleSubpage from "./settings/TeachByExampleSubpage";
import ReviewSubpage from "./settings/ReviewSubpage";
import PendingReviewSubpage from "./settings/PendingReviewSubpage";
import PersonaOnboardingSubpage from "./settings/PersonaOnboardingSubpage";
import TemplateSubpage from "./settings/TemplateSubpage";
import QrSubpage from "./settings/QrSubpage";
import { AddCircleOutline } from "antd-mobile-icons";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import PeopleAltOutlinedIcon from "@mui/icons-material/PeopleAltOutlined";
import PeopleAltIcon from "@mui/icons-material/PeopleAlt";
import MailOutlinedIcon from "@mui/icons-material/MailOutlined";
import MailIcon from "@mui/icons-material/Mail";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import { APP, FONT, ICON } from "../../theme";
import { useDoctorStore } from "../../../store/doctorStore";

// ── Tab config ─────────────────────────────────────────────────────

const TABS = [
  {
    key: "my-ai",
    label: "我的AI",
    icon: <AutoAwesomeOutlinedIcon sx={{ fontSize: "inherit" }} />,
    activeIcon: <AutoAwesomeIcon sx={{ fontSize: "inherit" }} />,
    path: "/doctor/my-ai",
    title: "我的AI",
  },
  {
    key: "patients",
    label: "患者",
    icon: <PeopleAltOutlinedIcon sx={{ fontSize: "inherit" }} />,
    activeIcon: <PeopleAltIcon sx={{ fontSize: "inherit" }} />,
    path: "/doctor/patients",
    title: "患者",
    badgeKey: "patients",
  },
  {
    key: "review",
    label: "审核",
    icon: <MailOutlinedIcon sx={{ fontSize: "inherit" }} />,
    activeIcon: <MailIcon sx={{ fontSize: "inherit" }} />,
    path: "/doctor/review",
    title: "审核",
    badgeKey: "review",
  },
];

// ── Section detection ──────────────────────────────────────────────

function detectSection(pathname) {
  // /doctor or /doctor/ → my-ai
  if (pathname === "/doctor" || pathname === "/doctor/") return "my-ai";
  const segment = pathname.split("/")[2]; // e.g. "my-ai", "patients", "review", "settings"
  if (TABS.some((t) => t.key === segment)) return segment;
  if (segment === "settings") return "settings";
  return "my-ai";
}

// ── Placeholder content ────────────────────────────────────────────

function SectionPlaceholder({ name }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        gap: 12,
        color: APP.text4,
        fontFamily: "system-ui, sans-serif",
        fontSize: FONT.md,
      }}
    >
      <span>{name} — 即将上线</span>
    </div>
  );
}

// ── Main shell ─────────────────────────────────────────────────────

export default function DoctorPage({ doctorId: propDoctorId, onLogout }) {
  const { doctorId: storeDoctorId } = useDoctorStore();
  const doctorId = propDoctorId || storeDoctorId;
  const location = useLocation();
  const navigate = useNavigate();

  const activeSection = detectSection(location.pathname);
  const activeTab = TABS.find((t) => t.key === activeSection) || TABS[0];

  // Badge counts — placeholder zeros; real data wired in later
  const [badges] = useState({ review: 0, patients: 0 });

  // Interview overlay — active when navigated to /doctor/patients/new
  const interviewActive = location.pathname.endsWith("/patients/new");

  // Optional preselected patient passed via ?patient_id=<id> when the user
  // picks an existing patient from the "新建病历" picker on MyAIPage.
  const interviewPatientIdParam = new URLSearchParams(location.search).get("patient_id");
  const { data: patientsForInterview } = usePatients();
  const interviewPatientContext = useMemo(() => {
    if (!interviewActive || !interviewPatientIdParam) return null;
    const list = Array.isArray(patientsForInterview)
      ? patientsForInterview
      : patientsForInterview?.items || [];
    const p = list.find((x) => String(x.id) === String(interviewPatientIdParam));
    return p ? { id: p.id, name: p.name } : null;
  }, [interviewActive, interviewPatientIdParam, patientsForInterview]);

  // Patient detail subpage — /doctor/patients/:id (any segment after /patients/ that isn't "new")
  const patientDetailMatch = (() => {
    const parts = location.pathname.split("/");
    // parts: ["", "doctor", "patients", ":id"]
    if (parts[2] === "patients" && parts[3] && parts[3] !== "new") {
      return parts[3];
    }
    return null;
  })();

  // Review detail subpage — /doctor/review/:recordId
  const reviewDetailMatch = (() => {
    const parts = location.pathname.split("/");
    // parts: ["", "doctor", "review", ":recordId"]
    if (parts[2] === "review" && parts[3]) {
      return parts[3];
    }
    return null;
  })();

  // Settings subpage detection
  // /doctor/settings → SettingsPage list
  // /doctor/settings/persona → PersonaSubpage
  // /doctor/settings/knowledge → KnowledgeSubpage
  // /doctor/settings/knowledge/add → AddKnowledgeSubpage
  // /doctor/settings/knowledge/:id → KnowledgeDetailSubpage
  // /doctor/settings/preferences → SettingsListSubpage
  const settingsMatch = (() => {
    const parts = location.pathname.split("/");
    if (parts[2] !== "settings") return null;
    const sub = parts[3]; // persona | knowledge | preferences | undefined
    const sub2 = parts[4]; // add | :id | undefined
    return { sub, sub2 };
  })();
  const settingsActive = !!settingsMatch;

  // Derive a unique route key for overlay subpages (null = tab root, no overlay)
  const overlayRouteKey = (() => {
    if (interviewActive) return "interview";
    if (patientDetailMatch) {
      // Tab changes within patient detail use ?view= with replace — same overlay key
      return `patient-${patientDetailMatch}`;
    }
    if (reviewDetailMatch) return `review-${reviewDetailMatch}`;
    if (settingsActive) {
      const { sub, sub2 } = settingsMatch;
      return `settings-${sub || "main"}${sub2 ? `-${sub2}` : ""}`;
    }
    return null;
  })();

  // Freeze the base tab content when an overlay is active/animating.
  // This prevents the tab underneath from switching (e.g., tasks → patients list)
  // while the overlay page slides in on top.
  const frozenSectionRef = useRef(activeSection);
  if (!overlayRouteKey) {
    frozenSectionRef.current = activeSection;
  }
  const baseSection = frozenSectionRef.current;

  // Render function for page stack — creates content for a given route key.
  // useCallback ensures stable reference so the stack doesn't re-render entries.
  const renderContent = useCallback((key) => {
    if (key === "interview") {
      return (
        <InterviewPage
          doctorId={doctorId}
          patientContext={interviewPatientContext}
          onComplete={() => navigate("/doctor/patients", { replace: true })}
          onCancel={() => navigate("/doctor/patients", { replace: true })}
        />
      );
    }
    if (key.startsWith("patient-")) {
      const id = key.replace("patient-", "");
      return <PatientDetail patientId={id} />;
    }
    if (key.startsWith("review-")) {
      return <ReviewPage recordId={key.replace("review-", "")} />;
    }
    if (key.startsWith("settings-")) {
      const parts = key.replace("settings-", "").split("-");
      const sub = parts[0];
      const sub2 = parts[1];
      if (sub === "persona" && sub2 === "pending") return <PendingReviewSubpage />;
      if (sub === "persona" && sub2 === "teach") return <TeachByExampleSubpage />;
      if (sub === "persona" && sub2 === "onboarding") return <PersonaOnboardingSubpage />;
      if (sub === "persona") return <PersonaSubpage />;
      if (sub === "knowledge" && (sub2 === "add" || sub2 === "new")) return <AddKnowledgeSubpage />;
      // Legacy redirect — pending rules now live inside the Knowledge tab (?tab=pending).
      if (sub === "knowledge" && sub2 === "pending") {
        return <Navigate to="/doctor/settings/knowledge?tab=pending" replace />;
      }
      if (sub === "knowledge" && sub2) return <KnowledgeDetailSubpage itemId={sub2} />;
      if (sub === "knowledge") return <KnowledgeSubpage />;
      if (sub === "preferences") return <SettingsListSubpage onLogout={onLogout} />;
      if (sub === "about") return <AboutSubpage />;
      if (sub === "teach") return <TeachByExampleSubpage />;
      if (sub === "review") return <ReviewSubpage />;
      if (sub === "pending") return <PendingReviewSubpage />;
      if (sub === "persona") return <PersonaOnboardingSubpage />;
      if (sub === "template" || sub === "templates") return <TemplateSubpage />;
      if (sub === "qr") return <QrSubpage />;
      return <SettingsPage />;
    }
    return null;
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Page stack — keeps previous pages mounted when navigating deeper
  const { stackEntries } = usePageStack(overlayRouteKey, renderContent);

  function handleTabChange(key) {
    const tab = TABS.find((t) => t.key === key);
    if (tab) navigate(tab.path, { replace: true });
  }

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Safe area top */}
      <SafeArea position="top" />

      {/* Top NavBar — hidden when stack active to prevent flash-through */}
      <NavBar
          backArrow={false}
          right={
            baseSection === "patients" ? (
              <Button
                fill="none"
                color="primary"
                size="small"
                onClick={() => navigate("/doctor/patients?action=new")}
                aria-label="新建病历"
              >
                <AddCircleOutline style={{ fontSize: ICON.md }} />
              </Button>
            ) : baseSection === "my-ai" ? (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div
                  aria-label="搜索"
                  style={{
                    padding: 8,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  <SearchOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />
                </div>
                <div
                  aria-label="通知"
                  style={{
                    padding: 8,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    position: "relative",
                  }}
                >
                  <NotificationsNoneOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />
                  <span
                    style={{
                      position: "absolute",
                      top: 7,
                      right: 7,
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      backgroundColor: APP.danger,
                    }}
                  />
                </div>
              </div>
            ) : null
          }
          style={{
            "--height": "44px",
            "--border-bottom": `0.5px solid ${APP.border}`,
            backgroundColor: APP.surface,
            flexShrink: 0,

          }}
        >
          {(TABS.find((t) => t.key === baseSection) || TABS[0]).title}
        </NavBar>

      {/* Content area */}
      <div
        style={{
          flex: 1,
          overflow: "hidden",
        }}
      >
        {/* Tab content — uses frozen section when overlay is active to prevent
            the base tab from switching while a subpage slides in on top */}
        {baseSection === "my-ai" ? (
          <MyAIPage doctorId={doctorId} />
        ) : baseSection === "patients" ? (
          <PatientsPage />
        ) : baseSection === "review" ? (
          <ReviewQueuePage />
        ) : (
          <SectionPlaceholder name={activeTab.title} />
        )}
      </div>

      {/* Page stack — positioned over the ENTIRE page (covers NavBar + TabBar) */}
      {stackEntries.map((entry) => (
        <div key={entry.key} style={entry.style}>
          {entry.content}
        </div>
      ))}

      {/* Bottom TabBar — hidden when stack active */}
      <div style={{ backgroundColor: APP.surface, flexShrink: 0 }} className="doctor-tabbar-wrap">
        <style>{`
          .doctor-tabbar-wrap .adm-tab-bar-item-active .adm-tab-bar-item-icon,
          .doctor-tabbar-wrap .adm-tab-bar-item-active .adm-tab-bar-item-title {
            color: ${APP.primary} !important;
          }
        `}</style>
        <TabBar
          safeArea
          activeKey={baseSection}
          onChange={handleTabChange}
          style={{
            borderTop: `0.5px solid ${APP.border}`,
            "--adm-color-primary": APP.primary,
          }}
        >
          {TABS.map((tab) => {
            const badgeCount = tab.badgeKey ? (badges[tab.badgeKey] || 0) : 0;
            const isActive = baseSection === tab.key;
            return (
              <TabBar.Item
                key={tab.key}
                icon={isActive ? tab.activeIcon : tab.icon}
                title={tab.label}
                badge={badgeCount > 0 ? badgeCount : undefined}
              />
            );
          })}
        </TabBar>
      </div>
    </div>
  );
}
