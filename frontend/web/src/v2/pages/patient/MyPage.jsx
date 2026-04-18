/**
 * MyPage — patient "我的" settings page (v2, antd-mobile).
 *
 * Business logic ported from src/pages/patient/MyPage.jsx.
 * Sections: patient info, doctor info, general (about/privacy/font), logout.
 */

import { useState } from "react";
import { Button, Dialog, List, Popup, Radio, Space } from "antd-mobile";
import {
  InformationCircleOutline,
  LoopOutline,
  TextOutline,
  UserOutline,
} from "antd-mobile-icons";
import { APP, FONT, RADIUS, applyFontScale } from "../../theme";

// ---------------------------------------------------------------------------
// Font scale store (inline — no MUI / v1 store dependency)
// ---------------------------------------------------------------------------

const FONT_SCALE_KEY = "v2_font_scale";

function getFontScale() {
  return localStorage.getItem(FONT_SCALE_KEY) || "large";
}

function setFontScaleStored(tier) {
  localStorage.setItem(FONT_SCALE_KEY, tier);
  applyFontScale(tier);
}

const FONT_SCALE_OPTIONS = [
  { key: "standard", label: "标准" },
  { key: "large", label: "大" },
  { key: "extraLarge", label: "特大" },
];

// ---------------------------------------------------------------------------
// Account avatar card
// ---------------------------------------------------------------------------

function AccountCard({ name, subtitle, color }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        padding: "12px 16px",
        background: APP.surface,
        borderBottom: `0.5px solid ${APP.border}`,
      }}
    >
      <div
        style={{
          width: 44,
          height: 44,
          borderRadius: RADIUS.circle,
          background: color || APP.primary,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginRight: 12,
          flexShrink: 0,
          color: APP.white,
          fontSize: 18,
          fontWeight: 700,
        }}
      >
        {name ? name.slice(-1) : "?"}
      </div>
      <div>
        <div style={{ fontSize: 16, fontWeight: 600, color: APP.text1 }}>{name || "—"}</div>
        {subtitle && (
          <div style={{ fontSize: FONT.sm, color: APP.text3, marginTop: 2 }}>{subtitle}</div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section label
// ---------------------------------------------------------------------------

function SectionLabel({ children }) {
  return (
    <div
      style={{
        padding: "12px 16px 4px",
        fontSize: 12,
        color: APP.text4,
        fontWeight: 600,
        background: APP.surfaceAlt,
      }}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// MyPage
// ---------------------------------------------------------------------------

const ONBOARDING_DONE_KEY_PREFIX = "patient_onboarding_done_";

export default function MyPage({ patientName, doctorName, doctorSpecialty, doctorId, onLogout }) {
  const [fontScale, setFontScale] = useState(getFontScale);
  const [showFontPopup, setShowFontPopup] = useState(false);

  function handleFontScaleChange(tier) {
    setFontScale(tier);
    setFontScaleStored(tier);
    setShowFontPopup(false);
  }

  function handleReplayOnboarding() {
    const patientId = localStorage.getItem("patient_portal_patient_id");
    if (patientId) localStorage.removeItem(ONBOARDING_DONE_KEY_PREFIX + patientId);
    window.location.reload();
  }

  function handleLogoutTap() {
    Dialog.confirm({
      title: "退出登录",
      content: "确定要退出登录吗？",
      cancelText: "取消",
      confirmText: "退出",
      onConfirm: onLogout,
    });
  }

  const currentFontLabel =
    FONT_SCALE_OPTIONS.find((o) => o.key === fontScale)?.label || "标准";

  return (
    <div style={{ flex: 1, overflowY: "auto", background: APP.surfaceAlt }}>
      {/* Patient info */}
      <SectionLabel>我的信息</SectionLabel>
      <AccountCard name={patientName || "患者"} subtitle="患者" color={APP.primary} />

      {/* Doctor info */}
      {doctorName && (
        <>
          <SectionLabel>我的医生</SectionLabel>
          <AccountCard
            name={doctorName}
            subtitle={doctorSpecialty || ""}
            color={APP.accent}
          />
        </>
      )}

      {/* General settings */}
      <SectionLabel>通用</SectionLabel>
      <List>
        <List.Item
          prefix={<InformationCircleOutline style={{ fontSize: 20, color: APP.text4 }} />}
          extra={
            <span style={{ fontSize: 13, color: APP.text4 }}>版本信息</span>
          }
          description={null}
          arrow
          onClick={() => {}}
        >
          关于
        </List.Item>
        <List.Item
          prefix={<UserOutline style={{ fontSize: 20, color: APP.text4 }} />}
          extra={
            <span style={{ fontSize: 13, color: APP.text4 }}>数据使用与保护</span>
          }
          description={null}
          arrow
          onClick={() => {}}
        >
          隐私政策
        </List.Item>
        <List.Item
          prefix={<TextOutline style={{ fontSize: 20, color: APP.text4 }} />}
          extra={
            <span style={{ fontSize: 13, color: APP.text4 }}>{currentFontLabel}</span>
          }
          description={null}
          arrow
          onClick={() => setShowFontPopup(true)}
        >
          字体大小
        </List.Item>
        <List.Item
          prefix={<LoopOutline style={{ fontSize: 20, color: APP.text4 }} />}
          description={null}
          arrow
          onClick={handleReplayOnboarding}
        >
          重新查看引导
        </List.Item>
      </List>

      {/* Logout */}
      <SectionLabel>账户操作</SectionLabel>
      <List>
        <List.Item
          onClick={handleLogoutTap}
          style={{ color: APP.danger, textAlign: "center", cursor: "pointer" }}
        >
          <span style={{ fontSize: FONT.md, color: APP.danger, fontWeight: 500 }}>退出登录</span>
        </List.Item>
      </List>

      <div style={{ height: 32 }} />

      {/* Font scale popup */}
      <Popup
        visible={showFontPopup}
        onMaskClick={() => setShowFontPopup(false)}
        position="bottom"
        bodyStyle={{ borderRadius: `${RADIUS.xl}px ${RADIUS.xl}px 0 0`, padding: "16px 16px 32px" }}
      >
        <div
          style={{
            textAlign: "center",
            fontSize: FONT.md,
            fontWeight: 600,
            color: APP.text1,
            marginBottom: 16,
          }}
        >
          字体大小
        </div>
        <Radio.Group
          value={fontScale}
          onChange={handleFontScaleChange}
        >
          <Space direction="vertical" style={{ width: "100%" }}>
            {FONT_SCALE_OPTIONS.map((o) => (
              <Radio
                key={o.key}
                value={o.key}
                style={{ width: "100%", fontSize: FONT.md }}
              >
                {o.label}
              </Radio>
            ))}
          </Space>
        </Radio.Group>
        <Button
          block
          color="default"
          style={{ marginTop: 16, borderRadius: RADIUS.md }}
          onClick={() => setShowFontPopup(false)}
        >
          取消
        </Button>
      </Popup>
    </div>
  );
}
