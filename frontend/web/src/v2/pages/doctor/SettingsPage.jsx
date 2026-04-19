/**
 * @route /doctor/settings
 *
 * SettingsPage v2 — doctor info, navigation to subpages, font scale, logout.
 * Mirrors v1: shows doctor profile + all settings in one page (no intermediate nav).
 */
import { NavBar, List, Button, Dialog, Avatar, Switch } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { useFontScaleStore, saveFontScaleToServer } from "../../../store/fontScaleStore";
import { useDoctorStore } from "../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";


export default function SettingsPage() {
  const navigate = useNavigate();
  const { fontScale, setFontScale } = useFontScaleStore();
  const { doctorId, doctorName } = useDoctorStore();

  const isLargeFont = fontScale === "large" || fontScale === "extraLarge";

  function handleFontToggle(checked) {
    const key = checked ? "large" : "standard";
    setFontScale(key);
    saveFontScaleToServer(doctorId);
  }

  function handleLogout() {
    Dialog.confirm({
      title: "退出登录",
      content: "确定要退出登录吗？",
      confirmText: "退出",
      cancelText: "取消",
      onConfirm: () => {
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
        {/* Doctor profile card */}
        <List style={{ marginBottom: 12 }}>
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
                      color: APP.white,
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

        {/* AI settings */}
        <List header="AI 助手">
          <List.Item arrow onClick={() => navigate("/doctor/settings/persona")}>
            AI人设
          </List.Item>
          <List.Item arrow onClick={() => navigate("/doctor/settings/knowledge")}>
            知识库
          </List.Item>
          <List.Item arrow onClick={() => navigate("/doctor/settings/template")}>
            回复模板
          </List.Item>
        </List>

        {/* General settings */}
        <List header="通用" style={{ marginTop: 12 }}>
          <List.Item extra={<Switch checked={isLargeFont} onChange={handleFontToggle} />}>
            大字模式
          </List.Item>
          <List.Item arrow onClick={() => navigate("/doctor/settings/about")}>
            关于
          </List.Item>
        </List>

        {/* Logout */}
        <div style={{ marginTop: 32, padding: "0 16px" }}>
          <Button block color="danger" fill="outline" onClick={handleLogout}>
            退出登录
          </Button>
        </div>

        <div style={{ height: 48 }} />
      </div>

    </div>
  );
}
