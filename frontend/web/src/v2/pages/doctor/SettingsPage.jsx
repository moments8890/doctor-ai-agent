/**
 * @route /doctor/settings
 *
 * SettingsPage v2 — card-based layout: profile card at top, AI 助手 group,
 * 通用设置 group, logout + security footer.
 */
import { NavBar, Button, Dialog, Switch } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import ChatBubbleOutlineIcon from "@mui/icons-material/ChatBubbleOutline";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import FormatSizeOutlinedIcon from "@mui/icons-material/FormatSizeOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import LogoutOutlinedIcon from "@mui/icons-material/LogoutOutlined";
import SecurityOutlinedIcon from "@mui/icons-material/SecurityOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { useFontScaleStore, saveFontScaleToServer } from "../../../store/fontScaleStore";
import { useDoctorStore } from "../../../store/doctorStore";
import { APP, FONT, RADIUS, ICON } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { NameAvatar, Card, TintedIconRow } from "../../components";

function SectionHeader({ Icon, iconColor, title }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "0 20px",
        margin: "16px 0 8px",
      }}
    >
      <Icon sx={{ fontSize: ICON.sm, color: iconColor }} />
      <span style={{ fontSize: FONT.base, color: APP.text3, fontWeight: 500 }}>
        {title}
      </span>
    </div>
  );
}

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
      <NavBar onBack={() => navigate(-1)} style={navBarStyle}>
        设置
      </NavBar>

      <div style={{ ...scrollable, paddingTop: 12, paddingBottom: 24 }}>
        {/* Doctor profile card — display-only, not tappable */}
        <Card>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "14px 16px",
            }}
          >
            <NameAvatar name={doctorName || "医"} size={48} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: FONT.lg, fontWeight: 700, color: APP.text1 }}>
                {doctorName || "医生"}
              </div>
              <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
                医生 · 主治医师
              </div>
            </div>
          </div>
        </Card>

        {/* AI 助手 */}
        <SectionHeader Icon={SmartToyOutlinedIcon} iconColor={APP.primary} title="AI 助手" />
        <Card>
          <TintedIconRow
            Icon={PsychologyOutlinedIcon}
            iconColor={APP.primary}
            iconBg={APP.primaryLight}
            title="AI 人设"
            subtitle="设置 AI 的角色与沟通风格"
            onClick={() => navigate("/doctor/settings/persona")}
            isFirst
          />
          <TintedIconRow
            Icon={MenuBookOutlinedIcon}
            iconColor={APP.primary}
            iconBg={APP.primaryLight}
            title="知识库"
            subtitle="管理 AI 使用的医学知识"
            onClick={() => navigate("/doctor/settings/knowledge")}
          />
          <TintedIconRow
            Icon={ChatBubbleOutlineIcon}
            iconColor={APP.primary}
            iconBg={APP.primaryLight}
            title="回复模板"
            subtitle="管理常用回复模板"
            onClick={() => navigate("/doctor/settings/template")}
          />
        </Card>

        {/* 通用设置 */}
        <SectionHeader Icon={SettingsOutlinedIcon} iconColor={APP.accent} title="通用设置" />
        <Card>
          <TintedIconRow
            Icon={FormatSizeOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="大字模式"
            subtitle="开启后界面文字更大更清晰"
            extra={<Switch checked={isLargeFont} onChange={handleFontToggle} />}
            isFirst
          />
          <TintedIconRow
            Icon={InfoOutlinedIcon}
            iconColor={APP.accent}
            iconBg={APP.accentLight}
            title="关于"
            subtitle="版本信息、隐私政策等"
            onClick={() => navigate("/doctor/settings/about")}
          />
        </Card>

        {/* Logout */}
        <div style={{ margin: "24px 12px 8px" }}>
          <Button
            block
            color="danger"
            fill="outline"
            onClick={handleLogout}
            style={{
              "--border-radius": `${RADIUS.lg}px`,
              padding: "14px 0",
              fontSize: FONT.md,
              fontWeight: 600,
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <LogoutOutlinedIcon sx={{ fontSize: ICON.sm }} />
              退出登录
            </span>
          </Button>
        </div>

        {/* Security footer */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            padding: "8px 16px",
            fontSize: FONT.sm,
            color: APP.text4,
          }}
        >
          <SecurityOutlinedIcon sx={{ fontSize: ICON.xs, color: APP.text4 }} />
          <span>退出后将清除本地缓存，确保账号安全</span>
        </div>
      </div>
    </div>
  );
}
