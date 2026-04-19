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
import { scrollable } from "../../layouts";
import { NameAvatar } from "../../components";

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
    <div style={scrollable}>
      {/* Patient info */}
      <List header="我的信息">
        <List.Item
          prefix={<NameAvatar name={patientName || "患者"} size={44} color={APP.primary} charPosition="last" />}
          description="患者"
        >
          {patientName || "患者"}
        </List.Item>
      </List>

      {/* Doctor info */}
      {doctorName && (
        <List header="我的医生">
          <List.Item
            prefix={<NameAvatar name={doctorName} size={44} color={APP.accent} charPosition="last" />}
            description={doctorSpecialty || ""}
          >
            {doctorName}
          </List.Item>
        </List>
      )}

      {/* General settings */}
      <List header="通用">
        <List.Item
          prefix={<InformationCircleOutline style={{ fontSize: 20, color: APP.text4 }} />}
          extra={
            <span style={{ fontSize: FONT.base, color: APP.text4 }}>版本信息</span>
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
            <span style={{ fontSize: FONT.base, color: APP.text4 }}>数据使用与保护</span>
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
            <span style={{ fontSize: FONT.base, color: APP.text4 }}>{currentFontLabel}</span>
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
      <List header="账户操作">
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
