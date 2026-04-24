/**
 * @route /doctor/settings/about
 *
 * AboutSubpage v2 — static about page. Card-based layout.
 */
import { NavBar } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { APP, FONT, ICON, RADIUS } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";

function SectionHeader({ title }) {
  return (
    <div
      style={{
        padding: "0 20px",
        margin: "16px 0 8px",
        fontSize: FONT.base,
        color: APP.text3,
        fontWeight: 500,
      }}
    >
      {title}
    </div>
  );
}

function Card({ children }) {
  return (
    <div
      style={{
        background: APP.surface,
        margin: "0 12px",
        borderRadius: RADIUS.lg,
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
}

function InfoRow({ label, value, isFirst }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "14px 16px",
        borderTop: isFirst ? "none" : `0.5px solid ${APP.borderLight}`,
      }}
    >
      <span style={{ fontSize: FONT.base, color: APP.text1, fontWeight: 500 }}>
        {label}
      </span>
      <span style={{ fontSize: FONT.base, color: APP.text3 }}>
        {value}
      </span>
    </div>
  );
}

export default function AboutSubpage() {
  const navigate = useNavigate();

  return (
    <div style={pageContainer}>
      <NavBar onBack={() => navigate(-1)} style={navBarStyle}>
        关于
      </NavBar>

      <div style={{ ...scrollable, paddingBottom: 24 }}>
        {/* App icon + branding card */}
        <div
          style={{
            background: APP.surface,
            margin: "12px 12px 0",
            borderRadius: RADIUS.lg,
            padding: "32px 24px 28px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            textAlign: "center",
          }}
        >
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: RADIUS.xl,
              backgroundColor: APP.primary,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: 16,
              fontSize: ICON.xl, // lint-ui-ignore: hero illustration (large initial)
              color: APP.white,
              fontWeight: 700,
            }}
          >
            医
          </div>
          <div style={{ fontSize: FONT.xl, fontWeight: 700, color: APP.text1, marginBottom: 6 }}>
            AI 医疗助手
          </div>
          <div style={{ fontSize: FONT.sm, color: APP.text4, marginBottom: 16 }}>
            版本 1.0.0
          </div>
          <div
            style={{
              fontSize: FONT.base,
              color: APP.text3,
              lineHeight: 1.7,
              maxWidth: 300,
            }}
          >
            智能医疗助手为医生提供 AI 辅助病历记录、患者管理和任务跟踪功能，帮助提升诊疗效率。
          </div>
        </div>

        {/* App info */}
        <SectionHeader title="应用信息" />
        <Card>
          <InfoRow label="版本号" value="1.0.0" isFirst />
          <InfoRow label="产品名称" value="医生AI助手" />
          <InfoRow label="AI 提供商" value="腾讯 · 通义千问" />
        </Card>
      </div>
    </div>
  );
}
