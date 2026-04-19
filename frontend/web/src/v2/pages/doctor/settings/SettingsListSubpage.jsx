/**
 * @route /doctor/settings/preferences
 *
 * SettingsListSubpage v2 — font scale, logout, about.
 * antd-mobile only, no MUI.
 */
import { useState } from "react";
import { NavBar, List, Popup, Button, Toast, Dialog, Avatar } from "antd-mobile";
import { CheckOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { useFontScaleStore, saveFontScaleToServer } from "../../../../store/fontScaleStore";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";

const FONT_SCALE_LEVELS = [
  { key: "standard",   label: "标准",     size: 14 },
  { key: "large",      label: "大字",     size: 17 },
  { key: "extraLarge", label: "特大字",   size: 19 },
];

export default function SettingsListSubpage({ onLogout }) {
  const navigate = useNavigate();
  const { fontScale, setFontScale } = useFontScaleStore();
  const { doctorId, doctorName } = useDoctorStore();
  const [fontScaleOpen, setFontScaleOpen] = useState(false);

  const currentFontLabel = FONT_SCALE_LEVELS.find((f) => f.key === fontScale)?.label || "标准";

  function handleSetFontScale(key) {
    setFontScale(key);
    saveFontScaleToServer(doctorId);
    setFontScaleOpen(false);
  }

  function handleLogout() {
    Dialog.confirm({
      title: "退出登录",
      content: "确定要退出登录吗？",
      confirmText: "退出",
      cancelText: "取消",
      onConfirm: () => {
        onLogout?.();
        useDoctorStore.getState().clearAuth();
        localStorage.removeItem("unified_auth_token");
        localStorage.removeItem("unified_auth_role");
        localStorage.removeItem("unified_auth_name");
        localStorage.removeItem("unified_auth_doctor_id");
        localStorage.removeItem("unified_auth_patient_id");
        window.location.href = "/login";
      },
    });
  }

  return (
    <div style={pageContainer}>
      <NavBar
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        设置
      </NavBar>

      <div style={scrollable}>
        {/* Account info */}
        <List style={{ marginBottom: 16 }}>
          <List.Item
            prefix={
              <Avatar
                src=""
                fallback={
                  <div
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: "50%",
                      backgroundColor: APP.primary,
                      color: APP.surface,
                      fontSize: FONT.lg,
                      fontWeight: 600,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {(doctorName || "医").charAt(0).toUpperCase()}
                  </div>
                }
                style={{ "--size": "48px", flexShrink: 0 }}
              />
            }
          >
            {doctorName || "医生"}
          </List.Item>
        </List>

        {/* General settings */}
        <List header="通用">
          <List.Item
            arrow
            description={currentFontLabel}
            onClick={() => setFontScaleOpen(true)}
          >
            字体大小
          </List.Item>
        </List>

        {/* About section */}
        <List header="关于" style={{ marginTop: 16 }}>
          <List.Item
            description="医生AI助手"
            arrow={false}
          >
            关于
          </List.Item>
        </List>

        {/* Logout */}
        <div style={{ marginTop: 32, padding: "0 16px" }}>
          <Button
            block
            color="danger"
            fill="outline"
            onClick={handleLogout}
          >
            退出登录
          </Button>
        </div>

        <div style={{ height: 48 }} />
      </div>

      {/* Font scale picker */}
      <Popup
        visible={fontScaleOpen}
        onMaskClick={() => setFontScaleOpen(false)}
        position="bottom"
        bodyStyle={{ borderRadius: "12px 12px 0 0" }}
      >
        <div style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
          <div
            style={{
              textAlign: "center",
              fontSize: FONT.md,
              fontWeight: 600,
              color: APP.text1,
              padding: "12px 0",
              borderBottom: `0.5px solid ${APP.border}`,
            }}
          >
            字体大小
          </div>
          <List>
            {FONT_SCALE_LEVELS.map((level) => {
              const active = fontScale === level.key;
              return (
                <List.Item
                  key={level.key}
                  onClick={() => handleSetFontScale(level.key)}
                  extra={active ? <CheckOutline style={{ color: APP.primary, fontSize: FONT.lg }} /> : null}
                  style={{ "--background-color": active ? APP.primaryLight : "transparent" }}
                >
                  <span
                    style={{
                      fontSize: level.size,
                      fontWeight: active ? 600 : 400,
                      color: active ? APP.primary : APP.text1,
                    }}
                  >
                    {level.label}
                  </span>
                </List.Item>
              );
            })}
          </List>
        </div>
      </Popup>
    </div>
  );
}
