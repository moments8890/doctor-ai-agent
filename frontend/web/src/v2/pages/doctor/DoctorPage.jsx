/**
 * @route /doctor/*
 *
 * v2 DoctorPage shell — antd-mobile TabBar + NavBar.
 * No MUI, no framer-motion, no complex subpage logic.
 * Placeholder content areas; real subpages wired in later tasks.
 *
 * IntakePage overlay: rendered when path is /doctor/patients/new
 */
import { useState, useCallback, useRef, useMemo } from "react";
import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { usePageStack } from "../../usePageStack";
import { NavBar, Popover, SafeArea, TabBar, Button, TextArea, Toast } from "antd-mobile";
import { usePatients } from "../../../lib/doctorQueries";
import IntakePage from "./IntakePage";
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
import AboutSubpage from "./settings/AboutSubpage";
import TeachByExampleSubpage from "./settings/TeachByExampleSubpage";
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
import AddToHomeScreenOutlinedIcon from "@mui/icons-material/AddToHomeScreenOutlined";
import FeedbackOutlinedIcon from "@mui/icons-material/FeedbackOutlined";
import { submitPlatformFeedback } from "../../../api";
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

// ── Feedback popover ───────────────────────────────────────────────
// Controlled antd-mobile Popover. Opens on icon tap, closes on submit
// success or outside click. Posts to /api/platform/feedback (auth via
// Authorization header from the existing api.js wrapper).
//
// Category chips are optional — selecting one prefixes the saved content
// with `[bug] ` / `[ui] ` / `[missing] ` so admin grep can pull them
// out without a schema migration. No category = naked content as before.

const FEEDBACK_CATEGORIES = [
  { key: "bug",     label: "Bug" },
  { key: "ui",      label: "UI 体验" },
  { key: "missing", label: "功能缺失" },
];

function CategoryChip({ active, label, onClick }) {
  return (
    <span
      role="button"
      onClick={onClick}
      style={{
        fontSize: FONT.sm,
        padding: "4px 10px",
        borderRadius: 12,
        cursor: "pointer",
        userSelect: "none",
        border: `1px solid ${active ? APP.primary : APP.border}`,
        color: active ? APP.primary : APP.text2,
        background: active ? `${APP.primary}14` : "transparent",
        transition: "all 100ms",
      }}
    >
      {label}
    </span>
  );
}

function FeedbackPopover({ children }) {
  const [visible, setVisible] = useState(false);
  const [category, setCategory] = useState(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  // Reset internal state every time the popover closes so a half-typed
  // draft doesn't surprise the user the next time they open it. (We
  // intentionally don't preserve drafts — feedback is small enough that
  // re-typing isn't a real cost.)
  function handleVisibleChange(next) {
    if (!next) {
      setCategory(null);
      setText("");
    }
    setVisible(next);
  }

  async function handleSubmit() {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      const tag = category ? `[${category}] ` : "";
      await submitPlatformFeedback({
        content: tag + trimmed,
        pageUrl: typeof window !== "undefined" ? window.location.href : null,
        userAgent: typeof navigator !== "undefined" ? navigator.userAgent : null,
      });
      Toast.show({ icon: "success", content: "已发送，谢谢你的反馈" });
      setCategory(null);
      setText("");
      setVisible(false);
    } catch (err) {
      Toast.show({
        icon: "fail",
        content: err?.message || "提交失败，请稍后再试",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Popover
      content={
        <div style={{ width: 280, padding: "4px 2px" }}>
          <div
            style={{
              fontSize: FONT.md,
              fontWeight: 600,
              color: APP.text1,
              marginBottom: 10,
            }}
          >
            反馈给我们
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
            {FEEDBACK_CATEGORIES.map((c) => (
              <CategoryChip
                key={c.key}
                active={category === c.key}
                label={c.label}
                onClick={() => setCategory(category === c.key ? null : c.key)}
              />
            ))}
          </div>
          <TextArea
            value={text}
            onChange={setText}
            placeholder="哪里有问题？想看到什么功能？任何想说的都可以"
            rows={4}
            maxLength={2000}
            autoSize={{ minRows: 4, maxRows: 8 }}
          />
          <Button
            color="primary"
            block
            size="small"
            loading={busy}
            disabled={!text.trim()}
            onClick={handleSubmit}
            style={{ marginTop: 8 }}
          >
            提交
          </Button>
        </div>
      }
      trigger="click"
      placement="bottomRight"
      visible={visible}
      onVisibleChange={handleVisibleChange}
    >
      {children}
    </Popover>
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

  // Intake overlay — active when navigated to /doctor/patients/new
  const intakeActive = location.pathname.endsWith("/patients/new");

  // Optional preselected patient passed via ?patient_id=<id> when the user
  // picks an existing patient from the "新建病历" picker on MyAIPage.
  const intakePatientIdParam = new URLSearchParams(location.search).get("patient_id");
  const { data: patientsForIntake } = usePatients();
  const intakePatientContext = useMemo(() => {
    if (!intakeActive || !intakePatientIdParam) return null;
    const list = Array.isArray(patientsForIntake)
      ? patientsForIntake
      : patientsForIntake?.items || [];
    const p = list.find((x) => String(x.id) === String(intakePatientIdParam));
    return p ? { id: p.id, name: p.name } : null;
  }, [intakeActive, intakePatientIdParam, patientsForIntake]);

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
  const settingsMatch = (() => {
    const parts = location.pathname.split("/");
    if (parts[2] !== "settings") return null;
    const sub = parts[3]; // persona | knowledge | undefined
    const sub2 = parts[4]; // add | :id | undefined
    return { sub, sub2 };
  })();
  const settingsActive = !!settingsMatch;

  // Derive a unique route key for overlay subpages (null = tab root, no overlay)
  const overlayRouteKey = (() => {
    if (intakeActive) return "intake";
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
    if (key === "intake") {
      return (
        <IntakePage
          doctorId={doctorId}
          patientContext={intakePatientContext}
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
      if (sub === "about") return <AboutSubpage />;
      if (sub === "teach") return <TeachByExampleSubpage />;
      if (sub === "pending") return <PendingReviewSubpage />;
      // Note: `sub === "review"` was removed — ReviewSubpage is a presentational
      // component that expects props (record + suggestions) and rendered blank
      // when navigated directly. Real review flow goes through /doctor/review/:id.
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
              <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
                <FeedbackPopover>
                  <div
                    role="button"
                    aria-label="反馈"
                    style={{
                      padding: 8,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                    }}
                  >
                    <FeedbackOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />
                  </div>
                </FeedbackPopover>
                <Popover
                  trigger="click"
                  placement="bottomRight"
                  content={
                    <div style={{ maxWidth: 240, padding: "4px 2px" }}>
                      <div
                        style={{
                          fontSize: FONT.md,
                          fontWeight: 600,
                          color: APP.text1,
                          marginBottom: 8,
                        }}
                      >
                        添加到桌面，下次一键打开
                      </div>
                      <div style={{ fontSize: FONT.sm, color: APP.text2, lineHeight: 1.7 }}>
                        <div>1. 点击微信右上角「···」</div>
                        <div>2. 选择「添加到桌面」</div>
                        <div>3. 下次直接从桌面打开</div>
                      </div>
                    </div>
                  }
                >
                  <div
                    role="button"
                    aria-label="添加到桌面"
                    style={{
                      padding: 8,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                    }}
                  >
                    <AddToHomeScreenOutlinedIcon sx={{ fontSize: ICON.md, color: APP.text2 }} />
                  </div>
                </Popover>
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
